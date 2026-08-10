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
**最近一次量測：37 個靶，35 殺掉、1 存活、0 靶壞**；唯一存活的「catalog 缺檔」經實測
確認是 *equivalent mutant*（拿掉那道 `is_file()` 前置檢查後，`cat.open()` 仍拋 `OSError`
被同一個 `except` 接住並報同一語意的錯、同樣 rc=1 —— 縱深防禦，不是缺口）。

> 這個數字**會過期**。判準不是相信這段話，而是跑一次 `mutation_check.py`。

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
        # 只複製閘門會碰到的部分，避免每個 test 都拷貝整棵樹（含 .git）
        for rel in (".claude-plugin",
                    "plugins/pai-lenses",
                    "plugins/parallel-ai-agents/.claude-plugin",
                    "plugins/parallel-ai-agents/bin",
                    "plugins/parallel-ai-agents/workflows",
                    "plugins/parallel-ai-agents/references",
                    "plugins/parallel-ai-agents/skills"):
            src, dst = REPO / rel, self.repo / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copytree(src, dst, symlinks=True)
        git(self.repo, "init", "-q", ".")
        git(self.repo, "config", "user.email", "t@t")
        git(self.repo, "config", "user.name", "t")

    def commit(self, msg="c"):
        git(self.repo, "add", "-A")
        git(self.repo, "-c", "commit.gpgsign=false", "commit", "-qm", msg)
        return git(self.repo, "rev-parse", "HEAD").stdout.strip()

    def run(self, *args, ci=False):
        """回傳 (rc, 合併後的輸出)。validate.py 把 error 印到 stdout（GitHub annotation）。

        `ci` 是**必要的參數，不是方便**（#33 verify R8 CRITICAL）：`check_bumped` 的
        no-base 分支依序是 workflow_dispatch → **`GITHUB_ACTIONS != "true"` 本機** → CI
        的 fail-loud。先前這裡寫死 `GITHUB_ACTIONS=""`，於是**每一條測試都走本機分支**，
        後面兩道全部被吃掉 —— 整段 no-base fail-loud（R4 的頭號修正）可以換成無條件
        `return` 而 26 條測試全綠，而名義上守 workflow_dispatch 的那條測試實際命中的是
        本機分支，是**套套邏輯的綠燈**。正是本檔開頭批判的那種測試。"""
        r = subprocess.run(
            [sys.executable, str(self.repo / "plugins/pai-lenses/scripts/validate.py"), *args],
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
        r = subprocess.run(
            [sys.executable, str(self.fx.repo / "plugins/lens-pack/scripts/validate.py"),
             "--base", base, "--event", "push"],
            cwd=self.fx.repo, capture_output=True, text=True,
            env={**os.environ, "GITHUB_ACTIONS": ""})
        out = r.stdout + r.stderr
        self.assertNotIn("新增整個 pack", out, f"改名不是新增：\n{out}")
        self.assertIn("改名", out, out)
        # R8 MEDIUM：先前只斷言訊息措辭。CHANGELOG 宣稱的是「用舊路徑比對，**閘門照跑**」——
        # 那句話要成立，就必須在這個 fixture（版本沒 bump）看到閘門真的擋下來。
        self.assertEqual(r.returncode, 1, f"閘門必須照跑：\n{out}")
        self.assertIn("版本沒有增加", out)

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
        """`seen == 0` 保險：一個沒有檢查到任何東西的閘門是形同虛設，不是通過。"""
        self.fx.set_entry("pai-lenses", source="https://example.com/a")
        self.fx.set_entry("parallel-ai-agents", source="https://example.com/b")
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

    def test_unknown_flag_is_usage_error(self):
        """R8：未知旗標先前被靜默丟棄 —— workflow 打錯旗標會安靜地換掉判準。"""
        rc, out = self.fx.run("--events", "push")
        self.assertEqual(rc, 2, out)
        self.assertIn("不認識的旗標", out)

if __name__ == "__main__":
    unittest.main(verbosity=2)
