#!/usr/bin/env python3
"""`validate.py` 的回歸測試（stdlib unittest —— CI 沒有裝 pytest，也不該為此加依賴）。

**為什麼需要這個檔**（#33 verify R7）：`validate.py` 有十餘道閘門，出貨時零測試覆蓋 ——
所有錯誤分支只在 CI 的 happy path 被執行（也就是**都沒被執行**）。#33 的六輪 verify 有
超過二十個 finding 落在這一支，其中反覆出現的形狀是「閘門在某個條件下安靜蒸發並印肯定式
綠燈」。那類缺陷用讀的抓不到，只有實際餵一份壞掉的 fixture 才會現形。

所以這裡的每一條測試都對應**一個已經真實發生過的缺陷**，而不是為了覆蓋率。

**這套測試自己的鑑別力是量出來的，不是宣稱的。** R8 的 devil's-advocate 實測指出：初版
26 條裡，20 個閘門 mutation **有 18 個存活** —— 包含 root `CLAUDE.md` 標為 CRITICAL 的版本
同步閘門，以及 R4 的頭號修正「拿不到 base → fail-loud」（後者甚至可以整段換成無條件
`return` 而全套仍綠）。而當時本檔開頭、`test.yml` 註解、CHANGELOG 三處都寫著「都做過
mutation」。**那三句話會讓下一個維護者以為改動 `validate.py` 有測試網接著。**

現在用 `scripts/mutation_check.py` 量：跑一次就知道哪些閘門沒有測試網。
**最近一次量測（R10 後）：56 個靶**（數字與存活清單請跑一次 `mutation_check.py`） —— 三個存活逐條實測後，
兩個是真缺口（已補測試，現在會轉紅），只有下面那個是 equivalent mutant；唯一存活的「catalog 缺檔」
經實測確認是 *equivalent mutant*（拿掉那道 `is_file()` 前置檢查後，`cat.open()` 仍拋
`OSError` 被同一個 `except` 接住並報同一語意的錯、同樣 rc=1 —— 縱深防禦，不是缺口）。

> 這個數字**會過期**。判準不是相信這段話，而是跑一次 `mutation_check.py`。
> CI 會跑 `--check-targets`（秒級），所以「靶清單與程式碼漂移」擋得住；
> 但「測試抓不抓得到」仍要手動跑完整輪。

跑法：`python3 scripts/test_validate.py`（在 pack 目錄下），或 `python3 -m unittest`。
"""
import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = pathlib.Path(__file__).resolve().parent
PACK = HERE.parent                      # plugins/pai-lenses
REPO = PACK.parent.parent               # monorepo root


def git(cwd, *args):
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True)


class Fixture:
    """一份真實 repo 的可寫複本 —— 閘門讀的是檔案系統與 git，mock 不了。"""

    def __init__(self):
        self.dir = pathlib.Path(tempfile.mkdtemp(prefix="pai-validate-"))
        self.repo = self.dir / "repo"
        # #33 verify R9 M21：先前用**寫死的目錄清單**，而 `.claude-plugin/marketplace.json`
        # 是整份複製進來的 —— 新增第三個 plugin 時 entry 進了 fixture、目錄沒進，
        # 於是**所有 assertGreen 測試同時轉紅**，訊息還指著一個在真實 repo 裡明明存在的
        # 路徑。諷刺的是那正是 root CLAUDE.md 這次新寫的賣點：「新增第三個 plugin 時
        # 自動涵蓋」—— 閘門確實自動涵蓋，測試 harness 不會。改成**枚舉 plugins/ 底下的
        # 每一個目錄**，只跳過與閘門無關又肥大的子樹。
        skip = {"eval", "test", "docs", "node_modules", "__pycache__", ".git"}
        (self.repo / "plugins").mkdir(parents=True, exist_ok=True)
        shutil.copytree(REPO / ".claude-plugin", self.repo / ".claude-plugin", symlinks=True)
        for plugin_dir in sorted((REPO / "plugins").iterdir()):
            if not plugin_dir.is_dir() or plugin_dir.name in skip:
                continue
            shutil.copytree(
                plugin_dir, self.repo / "plugins" / plugin_dir.name, symlinks=True,
                ignore=shutil.ignore_patterns(*skip))
        git(self.repo, "init", "-q", ".")
        git(self.repo, "config", "user.email", "t@t")
        git(self.repo, "config", "user.name", "t")

    def commit(self, msg="c"):
        git(self.repo, "add", "-A")
        git(self.repo, "-c", "commit.gpgsign=false", "commit", "-qm", msg)
        return git(self.repo, "rev-parse", "HEAD").stdout.strip()

    def run(self, *args, ci=False, script="plugins/pai-lenses/scripts/validate.py"):
        """回傳 (rc, 合併後的輸出)。validate.py 把 error 印到 stdout（GitHub annotation）。

        `ci` 是**必要的參數，不是方便**（#33 verify R8 CRITICAL）：`check_bumped` 的
        no-base 分支依序是 workflow_dispatch → **`GITHUB_ACTIONS != "true"` 本機** → CI
        的 fail-loud。先前這裡寫死 `GITHUB_ACTIONS=""`，於是**每一條測試都走本機分支**，
        後面兩道全部被吃掉 —— 整段 no-base fail-loud（R4 的頭號修正）可以換成無條件
        `return` 而 26 條測試全綠，而名義上守 workflow_dispatch 的那條測試實際命中的是
        本機分支，是**套套邏輯的綠燈**。正是本檔開頭批判的那種測試。"""
        r = subprocess.run(
            [sys.executable, str(self.repo / script), *args],
            cwd=self.repo, capture_output=True, text=True,
            env={**os.environ, "GITHUB_ACTIONS": "true" if ci else ""})
        return r.returncode, r.stdout + r.stderr

    def write_lenses(self, text, profile="code"):
        (self.repo / "plugins/pai-lenses/lenses" / f"{profile}.csv").write_text(
            text, encoding="utf-8")

    def edit_json(self, rel, fn):
        p = self.repo / rel
        d = json.loads(p.read_text(encoding="utf-8"))
        fn(d)
        p.write_text(json.dumps(d, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    def set_entry(self, name, **kw):
        def f(d):
            for e in d["plugins"]:
                if e.get("name") == name:
                    e.update(kw)
        self.edit_json(".claude-plugin/marketplace.json", f)

    def drop_entry(self, name):
        self.edit_json(".claude-plugin/marketplace.json",
                       lambda d: d.__setitem__(
                           "plugins", [e for e in d["plugins"] if e.get("name") != name]))

    def add_entry(self, name, source, version="9.9.9"):
        self.edit_json(".claude-plugin/marketplace.json",
                       lambda d: d["plugins"].append(
                           {"name": name, "source": source, "version": version}))

    def cleanup(self):
        shutil.rmtree(self.dir, ignore_errors=True)


class ValidateTest(unittest.TestCase):
    def setUp(self):
        self.fx = Fixture()
        self.addCleanup(self.fx.cleanup)

    def assertGreen(self, args=(), msg="", ci=False):
        rc, out = self.fx.run(*args, ci=ci)
        self.assertEqual(rc, 0, f"{msg}\n預期通過但 rc={rc}：\n{out}")
        return out

    def assertRed(self, args=(), contains=None, msg="", ci=False):
        rc, out = self.fx.run(*args, ci=ci)
        self.assertEqual(rc, 1, f"{msg}\n預期報錯但 rc={rc}：\n{out}")
        if contains:
            self.assertIn(contains, out, f"{msg}\n訊息不含預期字串：\n{out}")
        return out

    # ---- 基準：未動過的 repo 必須全綠。這條顧的是所有「壞輸入轉紅」測試的前提 ----
    def test_pristine_repo_passes(self):
        self.assertGreen(msg="未修改的 repo")

    # ---- check_version / semver（R7 M7：先前只驗 pack，主 plugin 一路綠燈）----
    def test_non_semver_version_is_error_for_pack_and_main_plugin(self):
        for rel, name in (("plugins/pai-lenses/.claude-plugin/plugin.json", "pai-lenses"),
                          ("plugins/parallel-ai-agents/.claude-plugin/plugin.json",
                           "parallel-ai-agents")):
            with self.subTest(plugin=name):
                fx = Fixture(); self.addCleanup(fx.cleanup)
                fx.edit_json(rel, lambda d: d.__setitem__("version", "not-semver"))
                fx.set_entry(name, version="not-semver")
                rc, out = fx.run()
                self.assertEqual(rc, 1, out)
                self.assertIn("semver", out)
                if name == "pai-lenses":
                    # #33 verify R10 H6：`check_version`（pack 自己那道）與
                    # `check_marketplace_sync` 的 per-plugin semver 檢查對同一份輸入都會叫，
                    # 所以只斷言「semver」的話，把 check_version 整道拿掉仍然全綠 ——
                    # 實測 57/57 通過。要釘住它，就得斷言**只有它會印的那句話**。
                    self.assertIn("需要 semver version", out,
                                  f"check_version 自己那道閘門必須有話說：\n{out}")

    # ---- 反向檢查（R6 H1 / DA：有目錄沒 entry 先前全綠）----
    def test_plugin_dir_without_marketplace_entry_is_error(self):
        self.assertGreen(msg="前提")
        self.fx.drop_entry("pai-lenses")
        self.assertRed(contains="沒有指向它的 entry")

    def test_new_plugin_dir_without_entry_is_error(self):
        d = self.fx.repo / "plugins/pai-extra/.claude-plugin"
        d.mkdir(parents=True)
        (d / "plugin.json").write_text('{"name":"pai-extra","version":"1.0.0"}\n')
        self.assertRed(contains="pai-extra")

    # ---- containment（R5 加、R6 發現只判到祖先目錄）----
    def test_absolute_and_dotdot_source_are_errors(self):
        for src in ("/tmp/elsewhere", "../elsewhere"):
            with self.subTest(source=src):
                fx = Fixture(); self.addCleanup(fx.cleanup)
                fx.set_entry("pai-lenses", source=src)
                rc, out = fx.run()
                self.assertEqual(rc, 1, out)
                self.assertIn("相對路徑", out)

    def test_symlinked_claude_plugin_dir_cannot_escape_repo(self):
        """R6 H4：containment 判定的是實際要讀的檔，不是它的祖先目錄。"""
        outside = self.fx.dir / "outside"
        outside.mkdir()
        (outside / "plugin.json").write_text('{"name":"evil","version":"9.9.9"}\n')
        evil = self.fx.repo / "plugins/evil"
        evil.mkdir(parents=True)
        (evil / ".claude-plugin").symlink_to(outside, target_is_directory=True)
        self.fx.add_entry("evil", "./plugins/evil")
        self.assertRed(contains="落在 repo 外")

    def test_illegal_entry_does_not_also_trigger_missing_entry_message(self):
        """R7 M12：被判非法的 entry 仍算「有人指名」，否則反向檢查會多報一則假訊息。"""
        evil = self.fx.repo / "plugins/evil/.claude-plugin"
        evil.mkdir(parents=True)
        (evil / "plugin.json").write_text('{"name":"evil","version":"9.9.9"}\n')
        self.fx.add_entry("evil", "plugins/evil/../evil")
        out = self.assertRed(contains="相對路徑")
        self.assertNotIn("沒有指向它的 entry", out)

    # ---- 遠端 source（R6 M9：白名單讓第三方 plugin 把 CI 弄紅）----
    def test_remote_sources_are_skipped_not_errors(self):
        for src in ("https://example.com/x", "ssh://git@github.com/o/r",
                    "github:o/r", "file:///tmp/x"):
            with self.subTest(source=src):
                fx = Fixture(); self.addCleanup(fx.cleanup)
                fx.add_entry("third-party", src)
                rc, out = fx.run()
                self.assertEqual(rc, 0, f"{src} 不該讓 CI 變紅：\n{out}")

    def test_ambiguous_source_warns_instead_of_silently_skipping(self):
        self.fx.add_entry("third-party", "owner/repo")
        out = self.assertGreen(msg="判不出來不該擋")
        self.assertIn("判不出", out)

    # ---- CSV 形狀 ----
    def test_short_row_is_allowed_but_missing_focus_is_not(self):
        """R5：省略尾端可選欄是 pack README 明文允許、生產端也解析得了的寫法。"""
        self.fx.write_lenses('key,focus,needsSrt,override\nperf,"a, b, c"\n')
        self.assertGreen(msg="省略尾端可選欄")
        self.fx.write_lenses("key,focus,needsSrt,override\nperf\n")
        self.assertRed(contains="缺 key 或 focus")

    def test_dotfiles_in_lenses_dir_are_skipped(self):
        """R6 M8：一個 .DS_Store 先前就讓貢獻者本機自檢 exit 1。"""
        (self.fx.repo / "plugins/pai-lenses/lenses/.DS_Store").write_bytes(b"\x00")
        self.assertGreen(msg="lenses/ 下的 dotfile")

    def test_unknown_header_column_is_error(self):
        self.fx.write_lenses('key,focus,overide\nperf,"x",true\n')
        self.assertRed(contains="不認識的欄位")

    # ---- 撞名（R6 H3 新增；R7 H1 發現真源讀不到時會蒸發）----
    def test_collision_with_builtin_without_override_is_error(self):
        self.fx.write_lenses('key,focus,needsSrt,override\nsecurity,"撞名",,\n')
        self.assertRed(contains="撞名")

    def test_collision_with_override_passes_but_warns(self):
        self.fx.write_lenses('key,focus,needsSrt,override\nsecurity,"刻意取代",,true\n')
        out = self.assertGreen(msg="標了 override")
        self.assertIn("取代", out)

    def test_duplicate_key_within_file_is_error(self):
        self.fx.write_lenses('key,focus\ndupe,"一"\ndupe,"二"\n')
        self.assertRed(contains="key 重複")

    def test_collision_gate_fails_loud_when_catalog_missing(self):
        """R7 H1：真源讀不到時先前整段跳過，還印肯定式「N 條 lens ✓」。"""
        (self.fx.repo
         / "plugins/parallel-ai-agents/references/builtin-lenses.csv").unlink()
        self.fx.write_lenses('key,focus\narchitecture,"撞名"\n')
        self.assertRed(contains="撞名閘門沒有跑")

    def test_collision_gate_fails_loud_when_catalog_header_changed(self):
        """R7 H1 的第二條路徑：header 缺 profile 欄時回 {} 而非 None，連保險都不觸發。"""
        cat = (self.fx.repo
               / "plugins/parallel-ai-agents/references/builtin-lenses.csv")
        lines = cat.read_text(encoding="utf-8").splitlines()
        lines[0] = "profileX,key,focus,needsSrt"
        cat.write_text("\n".join(lines) + "\n", encoding="utf-8")
        self.assertRed(contains="header 缺")

    # ---- profile 名稱閘門（R6 M7：工具不見時先前靜默蒸發）----
    def test_profile_gate_fails_loud_when_lister_missing(self):
        (self.fx.repo / "plugins/parallel-ai-agents/bin/pai-list-profiles").unlink()
        self.assertRed(contains="profile 名稱閘門沒有跑")

    def test_unknown_profile_filename_is_error(self):
        self.fx.write_lenses('key,focus\nx,"y"\n', profile="no-such-profile")
        self.assertRed(contains="不是既有 profile")

    # ---- bump 閘門 ----
    def test_changed_lens_without_bump_is_error_and_with_bump_passes(self):
        base = self.fx.commit("base")
        self.fx.write_lenses('key,focus\nperf,"新 lens"\n')
        self.fx.commit("改 lens，沒 bump")
        self.assertRed(("--base", base, "--event", "push"), contains="版本沒有增加")

        self.fx.edit_json("plugins/pai-lenses/.claude-plugin/plugin.json",
                          lambda d: d.__setitem__("version", "0.3.0"))
        self.fx.set_entry("pai-lenses", version="0.3.0")
        self.fx.commit("bump")
        out = self.assertGreen(("--base", base, "--event", "push"), msg="改 lens 且已 bump")
        self.assertIn("已 bump", out)

    def test_prerelease_to_final_counts_as_bump(self):
        """R7 M4：`0.3.0-rc1 → 0.3.0` 是最典型的發布動作，先前被判為未 bump。"""
        self.fx.edit_json("plugins/pai-lenses/.claude-plugin/plugin.json",
                          lambda d: d.__setitem__("version", "0.3.0-rc1"))
        self.fx.set_entry("pai-lenses", version="0.3.0-rc1")
        base = self.fx.commit("rc1")
        self.fx.write_lenses('key,focus\nperf,"新 lens"\n')
        self.fx.edit_json("plugins/pai-lenses/.claude-plugin/plugin.json",
                          lambda d: d.__setitem__("version", "0.3.0"))
        self.fx.set_entry("pai-lenses", version="0.3.0")
        self.fx.commit("rc → 正式版")
        self.assertGreen(("--base", base, "--event", "push"), msg="rc 轉正式版")

    def test_uncommitted_lens_change_is_surfaced_not_silently_green(self):
        """R6 H2：假綠燈出現在「無變更」那條路徑上，訊息必須在那裡也看得到。"""
        base = self.fx.commit("base")
        self.fx.write_lenses('key,focus\nperf,"尚未 commit"\n')
        out = self.assertGreen(("--base", base, "--event", "push"), msg="未 commit 的變更")
        self.assertIn("未 commit", out)

    def test_pack_rename_is_detected_not_reported_as_new_pack(self):
        """R7 M5：改名的那個 commit 先前走「新增整個 pack」那條，還說那是唯一合法情境。"""
        base = self.fx.commit("base")
        git(self.fx.repo, "mv", "plugins/pai-lenses", "plugins/lens-pack")
        self.fx.set_entry("pai-lenses", source="./plugins/lens-pack")
        self.fx.commit("改名")
        # 走 fx.run 而非自組 subprocess：R8 的 CRITICAL 根因就是環境在兩個地方各建一次，
        # 留一個平行入口等於把同一個坑重新挖好。改名後 script 路徑變了，用 script= 指定。
        rc, out = self.fx.run("--base", base, "--event", "push",
                              script="plugins/lens-pack/scripts/validate.py")
        self.assertNotIn("新增整個 pack", out, f"改名不是新增：\n{out}")
        self.assertIn("改名", out, out)
        # #33 verify R10 M3 更正：這裡先前斷言 `rc == 1` + 「版本沒有增加」——
        # 而這個 fixture 是**純改名**（一個 lens 字元都沒動）。也就是說這條測試
        # **把一個假陽性寫成了預期行為**：舊實作的變更清單那一側是 rename-blind，
        # 把搬移看成「每個 lens 都是新增」，於是要求為一次純目錄搬移 bump 版本。
        # M3 修掉那個假陽性之後，正確的預期是綠燈 + 明說偵測到純改名。
        # 「閘門照跑」由手足測試 test_rename_with_simultaneous_plugin_name_change…
        # 與 test_pure_rename_does_not_demand_a_bump 的第二段負責（那兩個有真的改內容）。
        self.assertEqual(rc, 0, f"純改名不該要求 bump：\n{out}")
        self.assertIn("純目錄改名", out)

    def test_missing_base_ref_is_error_not_silent_skip(self):
        self.assertRed(("--base", "0" * 40, "--event", "push"), contains="不在本地歷史內")

    def test_workflow_dispatch_without_base_is_not_an_error(self):
        """R5：一個結構上不可能綠的檢查，下一個人會直接把 fail-loud 拿掉。

        **必須帶 ci=True**：不帶的話命中的是「本機執行」分支，這條測試就與
        workflow_dispatch 無關（#33 verify R8 CRITICAL）。"""
        out = self.assertGreen(("--event", "workflow_dispatch"), msg="CI 手動觸發", ci=True)
        self.assertIn("workflow_dispatch", out)

    def test_ci_push_without_base_is_error(self):
        """R4 的頭號修正：push-to-main 沒有 base 時閘門結構性不存在。"""
        self.assertRed(("--event", "push"), contains="沒有跑", msg="CI push 無 base", ci=True)

    def test_ci_pull_request_without_base_is_error(self):
        self.assertRed(("--event", "pull_request"), contains="沒有 base ref",
                       msg="CI PR 無 base", ci=True)

    def test_local_run_without_base_is_a_note_not_an_error(self):
        """本機執行不該被擋 —— 但那是**因為它是本機**，不是因為沒人在看。"""
        out = self.assertGreen(msg="本機無 base", ci=False)
        self.assertIn("本機執行", out)

    # ---- 壞掉的 manifest 不可吃掉已累積的 annotation（R6 M5）----
    def test_broken_plugin_json_still_prints_accumulated_errors(self):
        base = self.fx.commit("base")
        self.fx.write_lenses('key,focus\nperf,"新"\n')
        self.fx.commit("改 lens")
        (self.fx.repo / "plugins/pai-lenses/.claude-plugin/plugin.json").write_text(
            "{ this is not json", encoding="utf-8")
        self.fx.commit("弄壞 plugin.json")
        rc, out = self.fx.run("--base", base, "--event", "push")
        self.assertEqual(rc, 1, out)
        self.assertNotIn("Traceback", out, f"不該是裸 traceback：\n{out}")
        self.assertGreaterEqual(out.count("::error"), 2,
                                f"先前的檢查已寫進 errs 的 annotation 必須印得出來：\n{out}")


    # ---- 版本同步：root CLAUDE.md 標為 CRITICAL 的那一條（R8 發現零覆蓋）----
    def test_one_sided_bump_is_error_and_two_sided_passes(self):
        """`plugins/pai-lenses/README.md` 對外承諾「只改一處 → CI 會擋」。先前那句沒有測試守。"""
        self.fx.edit_json("plugins/pai-lenses/.claude-plugin/plugin.json",
                          lambda d: d.__setitem__("version", "0.3.0"))
        self.assertRed(contains="version 不同步", msg="只改 plugin.json")
        self.fx.set_entry("pai-lenses", version="0.3.0")
        self.assertGreen(msg="兩處都改")

    def test_version_missing_on_both_sides_is_not_treated_as_in_sync(self):
        """R4：`mp_ver != pj_ver` 先前把「兩邊都沒有」判為一致並印 ✓ —— 而那正是 pack 會靜默消失的條件。"""
        self.fx.edit_json("plugins/pai-lenses/.claude-plugin/plugin.json",
                          lambda d: d.pop("version", None))
        def drop(d):
            for e in d["plugins"]:
                if e.get("name") == "pai-lenses":
                    e.pop("version", None)
        self.fx.edit_json(".claude-plugin/marketplace.json", drop)
        self.assertRed(contains="缺 version")

    def test_no_in_repo_plugin_checked_is_error(self):
        """`seen == 0` 保險：一個沒有檢查到任何東西的閘門是形同虛設，不是通過。

        entry 名稱**動態枚舉**，不寫死 —— 寫死兩個名字的話，新增第三個 plugin 就會讓
        這條測試紅掉（它的 source 仍是本地、`seen` 不為 0），而那是測試不夠 general，
        不是產品有問題。這條測試自己就是 M21 那類脆弱性的一個實例。"""
        def all_remote(d):
            for i, e in enumerate(d["plugins"]):
                e["source"] = f"https://example.com/{i}"
        self.fx.edit_json(".claude-plugin/marketplace.json", all_remote)
        self.assertRed(contains="形同虛設")

    def test_description_drift_warns(self):
        self.fx.set_entry("pai-lenses", description="與 plugin.json 不同的敘述")
        out = self.assertGreen(msg="description 不同步不該擋")
        self.assertIn("description 兩處不同步", out)

    # ---- CSV 形狀：每一條都對應一個「看起來像合法 lens、實際不會被載入」的形狀 ----
    def test_duplicate_header_column_is_error(self):
        self.fx.write_lenses('key,focus,key\nperf,"x",y\n')
        self.assertRed(contains="重複欄位")

    def test_unquoted_comma_in_focus_is_error(self):
        """pack README 明列的頭號陷阱：focus 的逗號沒 quote → 欄位錯位、focus 被截斷。"""
        self.fx.write_lenses('key,focus,needsSrt,override\nperf,檢查 a, b, c,,\n')
        self.assertRed(contains="欄位數多於 header")

    def test_wholesale_copied_catalog_header_is_error(self):
        """整份複製 builtin-lenses.csv：key 欄拿到 profile 名、focus 欄拿到 key，每列看起來仍合法。"""
        self.fx.write_lenses('profile,key,focus,needsSrt\ncode,architecture,"x",\n')
        self.assertRed(contains="builtin-lenses.csv 的格式")

    def test_zero_lenses_parsed_is_error(self):
        self.fx.write_lenses("key,focus\n")
        self.assertRed(contains="0 條 lens")

    def test_key_starting_with_hash_is_error(self):
        """CSV 沒有註解語法 —— 那一列會變成一條真的 lens 送進 reviewer prompt。"""
        self.fx.write_lenses('key,focus\n# 這是註解,"x"\nperf,"y"\n')
        self.assertRed(contains="'#' 開頭")

    def test_subdirectory_in_lenses_is_error(self):
        (self.fx.repo / "plugins/pai-lenses/lenses/sub").mkdir()
        self.assertRed(contains="不能有子目錄")

    def test_uppercase_csv_extension_is_error(self):
        """consumer 用 <profile>.csv 精確比對 —— 大小寫不同的檔案不會被載入。"""
        (self.fx.repo / "plugins/pai-lenses/lenses/academic.CSV").write_text(
            'key,focus\nx,"y"\n', encoding="utf-8")
        self.assertRed(contains="小寫 .csv")

    def test_missing_lenses_dir_is_error(self):
        shutil.rmtree(self.fx.repo / "plugins/pai-lenses/lenses")
        self.assertRed(contains="找不到")

    def test_lenses_dir_with_no_csv_is_error(self):
        for f in (self.fx.repo / "plugins/pai-lenses/lenses").iterdir():
            f.unlink()
        self.assertRed(contains="沒有任何合法")

    def test_unrecognised_truthy_value_warns(self):
        """`override=maybe` 會被當成 false —— 貢獻者以為標了。"""
        self.fx.write_lenses('key,focus,needsSrt,override\nperf,"x",,maybe\n')
        out = self.assertGreen(msg="無法辨識的真假值不該擋")
        self.assertIn("不是可辨識的真假值", out)

    # ---- 真源工具的失敗模式 ----
    def test_lister_succeeding_with_empty_output_is_error(self):
        """rc=0 但空輸出 → known_profiles 是空 set → 每個 CSV 都被報「不是既有 profile（真源有：）」。"""
        lister = self.fx.repo / "plugins/parallel-ai-agents/bin/pai-list-profiles"
        lister.write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")
        self.assertRed(contains="沒有輸出任何 profile")

    def test_catalog_parsing_to_zero_rows_is_error(self):
        cat = self.fx.repo / "plugins/parallel-ai-agents/references/builtin-lenses.csv"
        cat.write_text("profile,key,focus,needsSrt\n", encoding="utf-8")
        self.assertRed(contains="0 條 built-in lens")

    def test_malformed_argv_is_always_a_usage_error(self):
        """argv 的每一個洞，後果都是**安靜地換掉判準**（R8 起，R9 補完）。

        R8 只讓未知**旗標**（`-` 開頭）fail-loud —— 那是同一個缺陷的一半，因為 workflow
        實際傳的是旗標**值**。R9 實測：漏打 `--event`（`--base <sha> push`）時 `push` 被當
        位置參數丟棄、event 變 None → 走 merge-base 而非 exact-tree，在 force-push 情境下
        印出 `無需 bump ✓` exit 0，而正確呼叫報「版本沒有增加」exit 1。
        **R5 修掉的漏檢經由 argv 層原樣復活。** 現在一律由 argparse 擋。"""
        for args, label in [
            (("--events", "push"), "未知旗標"),
            (("--base", "HEAD", "push"), "漏打 --event（值變成位置參數）"),
            (("--event", "--base", "HEAD"), "旗標值是另一個旗標"),
            (("--event", "pusch"), "--event 不在列舉內"),
            (("--base", "HEAD", "garbage"), "多餘的位置參數"),
            (("--base",), "旗標缺值"),
        ]:
            with self.subTest(case=label):
                rc, out = self.fx.run(*args)
                self.assertEqual(rc, 2, f"{label} 必須是用法錯誤：\n{out}")

    def test_event_semantics_differ_between_push_and_default(self):
        """`--event` 的語意分流是本 PR 兩個世代修正的核心，先前**零測試覆蓋**（R9 H11）。

        建構 force-push 的分岔歷史：A 有 lens L1；B（舊 main tip）改成 L2 並 bump；
        force-push 後的新 tip C 由 A 長出（L2 被回退、版本退回）。
        `--event push` 問「這次 push 讓 main 變成什麼」→ exact-tree → 看得到回退；
        缺省（merge-base）問「這個分支引入了什麼」→ 相對 A 沒有變更。
        兩個方向都要斷言，只驗其一的話把語意接反了也不會被抓到。"""
        self.fx.write_lenses('key,focus\nL1,"第一版"\n')
        a = self.fx.commit("A")
        self.fx.write_lenses('key,focus\nL2,"第二版"\n')
        self.fx.edit_json("plugins/pai-lenses/.claude-plugin/plugin.json",
                          lambda d: d.__setitem__("version", "0.3.0"))
        self.fx.set_entry("pai-lenses", version="0.3.0")
        b = self.fx.commit("B（舊 main tip）")
        git(self.fx.repo, "checkout", "-q", a)
        git(self.fx.repo, "checkout", "-qb", "forced")

        self.assertRed(("--base", b, "--event", "push"), contains="版本沒有增加",
                       msg="push＝exact-tree，必須看見 lens 被回退")
        out = self.assertGreen(("--base", b), msg="缺省＝merge-base，相對 A 確實沒有變更")
        self.assertIn("merge-base", out)

    # ---- entry 身分（R9 H2/M13：`name` 先前只出現在錯誤訊息裡，從不參與判定）----
    def test_entry_name_must_match_plugin_json_name(self):
        """訊息必須指名**哪一種**問題：缺 name 與 name 打錯的下游後果不同（一個是沒有名字
        可裝、一個是裝錯名字），只斷言 rc=1 的話把兩條分支合成一條也不會被抓到。"""
        for label, fn, expect in (
            ("缺 name", lambda e: e.pop("name", None), "沒有 name"),
            ("name 打錯", lambda e: e.update(name="pai-lense"), "不一致"),
        ):
            with self.subTest(case=label):
                fx = Fixture(); self.addCleanup(fx.cleanup)
                def edit(d, fn=fn):
                    for e in d["plugins"]:
                        if str(e.get("source", "")).endswith("pai-lenses"):
                            fn(e)
                fx.edit_json(".claude-plugin/marketplace.json", edit)
                rc, out = fx.run()
                self.assertEqual(rc, 1, f"{label}：\n{out}")
                self.assertIn(expect, out, f"{label} 的訊息要指名問題：\n{out}")

    def test_duplicate_entry_name_is_error(self):
        self.fx.add_entry("pai-lenses", "./plugins/pai-lenses", version="0.2.0")
        self.assertRed(contains="entry name 'pai-lenses' 重複", msg="同名 entry")

    def test_two_entries_pointing_at_the_same_dir_is_error(self):
        """名字不同、source 相同 —— 只有這個形狀能單獨驗到路徑重複那道檢查。
        先前的測試同時撞名又撞路徑，撞名那道就把它蓋掉了（#33 verify R9 mutation 存活）。"""
        self.fx.add_entry("some-other-name", "./plugins/pai-lenses", version="0.2.0")
        self.assertRed(contains="指向同一個目錄")

    # ---- lenses/ 的讀取面（R9 H1/M17 + H5）----
    def test_symlink_in_lenses_is_rejected_without_leaking_content(self):
        secret = self.fx.dir / "secret.txt"
        secret.write_text("TOP-SECRET-FIRST-LINE\n", encoding="utf-8")
        (self.fx.repo / "plugins/pai-lenses/lenses/leak.csv").symlink_to(secret)
        out = self.assertRed(contains="不能有 symlink")
        self.assertNotIn("TOP-SECRET", out, "目標檔內容不可進 CI annotation")

    def test_hidden_files_are_triaged_into_three_kinds(self):
        """封閉列舉的三種處置各驗一次（#33 verify R9）：已知 OS 產物靜默略過、
        隱藏的 `.csv` 報錯（它看起來像 lens 但不會被載入）、其他未知隱藏檔印 warning
        而不是把整支擋掉。只驗前兩種的話，第三種被改成 error 也不會被抓到。"""
        lenses = self.fx.repo / "plugins/pai-lenses/lenses"
        (lenses / ".DS_Store").write_bytes(b"\x00")
        out = self.assertGreen(msg="OS 產物照舊略過")
        # #33 verify R10 H7：先前只斷言 rc=0 —— 把白名單整條拿掉，`.DS_Store` 會落到
        # 「不認識的隱藏檔」那條印一則 warning，rc 仍是 0，**測試照樣綠**。
        # 白名單的價值是「**靜默**略過已知 OS 產物」，所以測試必須斷言靜默。
        self.assertNotIn(".DS_Store", out, f"已知 OS 產物必須靜默略過：\n{out}")

        (lenses / ".foo").write_text("x", encoding="utf-8")
        out = self.assertGreen(msg="未知隱藏檔不該擋下整支")
        self.assertIn("不認識的隱藏檔", out)
        (lenses / ".foo").unlink()

        (lenses / ".lecture.csv").write_text('key,focus\nx,"y"\n', encoding="utf-8")
        self.assertRed(contains="隱藏的 .csv")

    # ---- manifest 型別（R9 H7：R6 M5 的第二個站點）----
    def test_valid_json_of_wrong_type_does_not_crash(self):
        """R6 M5 只覆蓋語法壞掉的 JSON。合法 JSON 但不是物件會拋 AttributeError ——
        不在任何 except 裡，整支 crash，已累積的 annotation 一條都印不出來。"""
        for rel, label in (
            ("plugins/pai-lenses/.claude-plugin/plugin.json", "pack plugin.json"),
            ("plugins/parallel-ai-agents/.claude-plugin/plugin.json", "主 plugin.json"),
            (".claude-plugin/marketplace.json", "marketplace.json"),
        ):
            with self.subTest(file=label):
                fx = Fixture(); self.addCleanup(fx.cleanup)
                (fx.repo / rel).write_text("[]", encoding="utf-8")
                rc, out = fx.run()
                self.assertEqual(rc, 1, out)
                self.assertNotIn("Traceback", out, f"{label} 不該是裸 traceback：\n{out}")
                self.assertIn("::error", out, f"{label} 必須留下 annotation：\n{out}")

    def test_marketplace_plugins_of_wrong_type_does_not_crash(self):
        self.fx.edit_json(".claude-plugin/marketplace.json",
                          lambda d: d.__setitem__("plugins", ["pai-lenses"]))
        out = self.assertRed()
        self.assertNotIn("Traceback", out)

    def test_plugins_not_a_list_gives_one_clear_error_not_a_cascade(self):
        """`plugins` 是 dict 時，沒有前置守衛也不會 crash —— `for entry in plugins` 會迭代
        key，每個 key 都不是 dict，於是報一串「元素不是物件」。rc 相同、也沒有 traceback，
        所以只斷言 rc 的測試分辨不出來。這道守衛的價值是**一則說對原因的訊息**。"""
        self.fx.edit_json(".claude-plugin/marketplace.json",
                          lambda d: d.__setitem__("plugins", {"pai-lenses": {}}))
        out = self.assertRed(contains="`plugins` 必須是陣列")
        self.assertEqual(out.count("::error"), 1, f"應該只有一則訊息：\n{out}")

    # ---- 改名偵測（R9 H8：先前綁在 plugin.json 的 name 上）----
    def test_rename_with_simultaneous_plugin_name_change_is_still_detected(self):
        """目錄改名同時改 plugin 名是很常見的一個 PR。先前 `_find_pack_at` 只比 `name`，
        於是整條偵測失效並印「這是唯一合法的略過情境」—— 那句話在這條路徑上是假的。"""
        base = self.fx.commit("base")
        git(self.fx.repo, "mv", "plugins/pai-lenses", "plugins/lens-pack")
        self.fx.edit_json("plugins/lens-pack/.claude-plugin/plugin.json",
                          lambda d: d.__setitem__("name", "lens-pack"))
        def ent(d):
            for e in d["plugins"]:
                if e.get("name") == "pai-lenses":
                    e.update(name="lens-pack", source="./plugins/lens-pack")
        self.fx.edit_json(".claude-plugin/marketplace.json", ent)
        (self.fx.repo / "plugins/lens-pack/lenses/code.csv").write_text(
            'key,focus\nnew,"改名後新增，沒 bump"\n', encoding="utf-8")
        self.fx.commit("改名 + 改 plugin 名 + 加 lens，不 bump")
        rc, out = self.fx.run("--base", base, "--event", "push",
                              script="plugins/lens-pack/scripts/validate.py")
        self.assertNotIn("新增整個 pack", out, f"改名不是新增：\n{out}")
        self.assertEqual(rc, 1, f"閘門必須照跑：\n{out}")
        self.assertIn("版本沒有增加", out)

    # ---- semver 嚴格度與 prerelease 排序（R9 H4）----
    def test_semver_is_strict_and_prerelease_ordering_follows_spec(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location("v", str(PACK / "scripts/validate.py"))
        v = importlib.util.module_from_spec(spec); spec.loader.exec_module(v)
        for bad in ("01.2.3", "1.2.3-", "1.2.3+", "1.2.3\n", "v1.2.3", "1.2"):
            self.assertIsNone(v.version_tuple(bad), f"{bad!r} 不該被當成合法 semver")
        self.assertIsNotNone(v.version_tuple("1.2.3-alpha.1+build.5"))
        # semver §11：prerelease < 同 core 正式版；數字段按整數比較
        self.assertLess(v.version_tuple("1.0.0-rc.1"), v.version_tuple("1.0.0"))
        self.assertLess(v.version_tuple("1.0.0-beta.2"), v.version_tuple("1.0.0-beta.11"))
        self.assertLess(v.version_tuple("1.0.0-alpha"), v.version_tuple("1.0.0-alpha.1"))

    def test_check_bumped_json_sites_also_guard_type(self):
        """#33 verify R10 H2/M11：R9 把三個 JSON 讀取點改走 `load_obj`，漏了 `check_bumped`
        裡的兩個。而先前那條「型別不對不 crash」的測試**結構上到不了那裡** —— 它不帶
        `--base`，bump 檢查根本沒跑。要驗到就必須造出「有 base、lens 有變更、
        然後 plugin.json 是非 dict」的路徑。"""
        base = self.fx.commit("base")
        self.fx.write_lenses('key,focus\nperf,"新 lens"\n')
        (self.fx.repo / "plugins/pai-lenses/.claude-plugin/plugin.json").write_text(
            '["not","an","object"]', encoding="utf-8")
        self.fx.commit("改 lens + 把 plugin.json 換成陣列")
        rc, out = self.fx.run("--base", base, "--event", "push")
        self.assertNotIn("Traceback", out, f"不該是裸 traceback：\n{out}")
        self.assertEqual(rc, 1, out)
        self.assertIn("::error", out, f"必須留下 annotation：\n{out}")

    def test_lenses_dir_itself_cannot_be_a_symlink_out_of_repo(self):
        """#33 verify R10 H4：R9 的 symlink 守衛只作用在 `lenses/` 的**條目**上，
        目錄自己是 symlink 時整個逃逸 —— 實測會把 repo 外目錄的檔名逐一印進 annotation，
        並讀取其中的檔案把第一行印出來。"""
        outside = self.fx.dir / "outside"
        outside.mkdir()
        (outside / "secret.csv").write_text("SECRET-HEADER-LINE\n", encoding="utf-8")
        lenses = self.fx.repo / "plugins/pai-lenses/lenses"
        shutil.rmtree(lenses)
        lenses.symlink_to(outside, target_is_directory=True)
        out = self.assertRed(contains="落在 repo 外")
        self.assertNotIn("SECRET-HEADER-LINE", out, "目標檔內容不可進 CI annotation")
        self.assertNotIn("secret.csv", out, "repo 外的檔名也不可外洩")

    def test_prerelease_with_glued_digits_warns(self):
        """`rc9` 這種把數字黏在字母後面的 identifier，semver 規定按 ASCII 比較 ——
        於是 `rc9 > rc10`，遞增發布會被 bump 閘門擋下。程式碼合規，但陷阱要顯性化。"""
        self.fx.edit_json("plugins/pai-lenses/.claude-plugin/plugin.json",
                          lambda d: d.__setitem__("version", "0.3.0-rc9"))
        self.fx.set_entry("pai-lenses", version="0.3.0-rc9")
        out = self.assertGreen(msg="rcN 合法，只是有陷阱")
        self.assertIn("把數字黏在字母後面", out)

    def test_pure_rename_does_not_demand_a_bump(self):
        """#33 verify R10 M3：改名偵測先前只讓「舊版本」rename-aware，變更清單那一側
        仍用新路徑 —— 於是一次**純目錄搬移**（lens 內容零變動）被要求 bump。
        兩個方向都驗：純改名放行、改名時真的改了內容仍要擋。"""
        base = self.fx.commit("base")
        git(self.fx.repo, "mv", "plugins/pai-lenses", "plugins/lens-pack")
        def ent(d):
            for e in d["plugins"]:
                if e.get("name") == "pai-lenses":
                    e["source"] = "./plugins/lens-pack"
        self.fx.edit_json(".claude-plugin/marketplace.json", ent)
        self.fx.commit("純改名")
        script = "plugins/lens-pack/scripts/validate.py"
        rc, out = self.fx.run("--base", base, "--event", "push", script=script)
        self.assertEqual(rc, 0, f"純改名不該要求 bump：\n{out}")
        self.assertIn("純目錄改名", out)

        (self.fx.repo / "plugins/lens-pack/lenses/code.csv").write_text(
            'key,focus\nnew,"改名時也改了內容"\n', encoding="utf-8")
        self.fx.commit("再改 lens")
        rc, out = self.fx.run("--base", base, "--event", "push", script=script)
        self.assertEqual(rc, 1, f"改名 + 真的改了內容仍要擋：\n{out}")
        self.assertIn("版本沒有增加", out)

    def test_entry_with_wrong_source_says_fix_the_entry_not_add_one(self):
        """#33 verify R10 M4：source 形式不合時，反向檢查先前報「沒有指向它的 entry」——
        那會把維護者導向「再加一條 entry」這個**錯誤修法**，而真正的問題是既有那條寫錯了。
        真的缺 entry 時仍要說「沒有指向它的 entry」，兩者不可混。"""
        def bad_src(d):
            for e in d["plugins"]:
                if e.get("name") == "pai-lenses":
                    e["source"] = "pluginz/pai-lenses"
        self.fx.edit_json(".claude-plugin/marketplace.json", bad_src)
        out = self.assertRed(contains="要修的是那條 entry 的 source")
        self.assertNotIn("沒有指向它的 entry", out)

        fx2 = Fixture(); self.addCleanup(fx2.cleanup)
        fx2.drop_entry("pai-lenses")
        rc2, out2 = fx2.run()
        self.assertEqual(rc2, 1, out2)
        self.assertIn("沒有指向它的 entry", out2, "真的缺 entry 時訊息不可被前一條蓋掉")

    def test_filename_cannot_inject_workflow_commands(self):
        """git 允許檔名含換行，而檔名會被插進幾乎每一則 annotation。

        #33 verify R10（作者自查）：R10 的第一版修法是在**個別呼叫點**包 `wc()` ——
        包了六處，而實際有約四十處插入攻擊者可控的值。**那個修法本身就是「同類只修一處」，
        只是規模更大。** 現在改成在**唯一的輸出出口** `emit()` 消毒：workflow command 必須
        從行首解析，所以保證一行永遠是一行就夠了。這條測試走的是 CSV 欄位以外的路徑，
        用來釘住「邊界修法涵蓋所有站點」這個性質。"""
        evil = (self.fx.repo / "plugins/pai-lenses/lenses"
                / "bad\n::stop-commands::zzz\n::error file=innocent.py,line=1::forged.txt")
        evil.write_text("x", encoding="utf-8")
        rc, out = self.fx.run()
        for line in out.splitlines():
            self.assertFalse(line.startswith("::stop-commands::"),
                             f"檔名不可注入 workflow command：\n{out}")
            self.assertFalse(line.startswith("::error file=innocent.py"),
                             f"不可偽造指向其他檔案的 annotation：\n{out}")

    def test_untrusted_content_cannot_inject_workflow_commands(self):
        """#33 verify R10 M8：CSV 的引號欄位可含真正的換行。未消毒地插進 `::warning::`
        就能多出一行 `::stop-commands::` —— runner 會停止解析後續所有 workflow command，
        包含 validator 自己排隊的每一條 `::error::`。job 仍紅，但 PR 上零 annotation：
        把本 PR 一路在建的 fail-loud 降級成 fail-silent。"""
        self.fx.write_lenses(
            'key,focus,needsSrt,override\n'
            'perf,"x","y\n::stop-commands::zzz\n::error file=innocent.py,line=1::forged",\n')
        rc, out = self.fx.run()
        for line in out.splitlines():
            self.assertFalse(line.strip().startswith("::stop-commands::"),
                             f"不可產生 ::stop-commands:: 行：\n{out}")
        self.assertNotIn("::error file=innocent.py", out, "不可偽造指向其他檔案的 annotation")

    def test_catalog_symlink_cannot_leak_content(self):
        """#33 verify R10：symlink 洩漏的第三個站點 —— catalog（`builtin-lenses.csv`）。
        **rc 兩邊都是 1**（缺檔／讀不到都會報「撞名閘門沒有跑」），差別只在目標檔內容有沒有
        被印進 annotation。只斷言 rc 的測試分辨不出來，所以這裡斷言的是**外洩本身**。"""
        outside = self.fx.dir / "outside.csv"
        outside.write_text("SECRET-CATALOG-HEADER\n", encoding="utf-8")
        cat = self.fx.repo / "plugins/parallel-ai-agents/references/builtin-lenses.csv"
        cat.unlink()
        cat.symlink_to(outside)
        out = self.assertRed(contains="落在 repo 外")
        self.assertNotIn("SECRET-CATALOG-HEADER", out, "目標檔內容不可進 CI annotation")

    def test_base_side_manifest_of_wrong_type_also_guarded(self):
        """`check_bumped` 有**兩個** JSON 讀取點：HEAD 那側與 base 那側。
        先前的測試只把 HEAD 的 plugin.json 換成陣列，結構上到不了 base 那側 ——
        「兩個站點」的第二個仍然沒有測試網（#33 verify R10 mutation 存活）。"""
        (self.fx.repo / "plugins/pai-lenses/.claude-plugin/plugin.json").write_text(
            '["not","an","object"]', encoding="utf-8")
        base = self.fx.commit("base 的 plugin.json 是陣列")
        self.fx.edit_json(".claude-plugin/marketplace.json", lambda d: None)
        (self.fx.repo / "plugins/pai-lenses/.claude-plugin/plugin.json").write_text(
            '{"name":"pai-lenses","version":"0.3.0"}\n', encoding="utf-8")
        self.fx.write_lenses('key,focus\nperf,"新 lens"\n')
        self.fx.commit("修好 plugin.json + 改 lens")
        rc, out = self.fx.run("--base", base, "--event", "push")
        self.assertNotIn("Traceback", out, f"base 那側也不該是裸 traceback：\n{out}")
        self.assertEqual(rc, 1, out)
        self.assertIn("::error", out)

if __name__ == "__main__":
    unittest.main(verbosity=2)
