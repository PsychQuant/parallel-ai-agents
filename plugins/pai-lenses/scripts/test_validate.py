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
**最近一次量測（R15 後）：96 個靶 → 93 殺 / 0 存活 / 0 靶壞**（另 3 個 `EXPECTED_SURVIVE`，不計入存活；
數字與存活清單請跑一次 `mutation_check.py`——一輪約 30–40 分鐘）。**這是複合值，明寫**：全輪跑的是 DA 修補前的
副本（94 靶）→ 89 殺／2 存活（「沒有合法 csv」與「check_csvs 沒有跑的具名訊息」——main() 新加的 `[]` 訊息與
它們各自的訊息共用了「沒有任何合法」／「check_csvs 沒有跑」字串，測試補斷言具名原因後單靶重跑轉殺）；DA 修補新增的
2 靶（NO_REPO_GATES 少列一道、base 字串經 wc()）各自單獨驗殺。斷言只加嚴、已殺者不會復活，但下一輪請重跑全輪。
R15 新增 4 個靶（check_csvs 空清單的具名訊息、profile 清單經 wc()、NO_REPO_GATES 少列一道、merge-base stderr 經 wc()），各自單獨驗過會被殺。R14 的量測是
88 殺／1 存活（「lister 不存在」在 stderr 不再進 annotation 後與 rc=127 的訊息只差在說對原因，補斷言後單靶重跑轉殺）。
`EXPECTED_SURVIVE` 3 個：`_find_pack_at` git 分支的兩個守衛依構造不可達（R12 logic L3 / DA-6，保留為防禦）、
「換回 splitlines()」（LineSanitiser 對每一段獨立判定，過度切段只會過度消毒）。規則明寫在 mutation_check.py：每一條
進來的靶都要能回答「關掉它，哪一行輸出會變」（R14 把「pack_name 讀取的 containment」放進去的理由是假的——
dirty worktree 到得了那行 print——現在它有測試網）。
R13 修法的 `main()` 逐閘門隔離曾讓一輪跑出 8 個假存活（守衛被刪掉後只剩一條「validator 內部錯誤」），修在
`Fixture.run`（預設拒絕那個字串）一處；R12 曾判「catalog 缺檔」為 equivalent——不是：守衛的價值是**說對原因**。
R11 曾寫「四個存活皆 equivalent」：一個判定為假（containment 靶，已補 `./docs/evil` fixture 轉紅）、
兩個理由為假（那兩個是死碼，不是互為後盾）。

> 這個數字**會過期**。判準不是相信這段話，而是跑一次 `mutation_check.py`。
> CI 會跑 `--check-targets`（秒級），所以「靶清單與程式碼漂移」擋得住；
> 但「測試抓不抓得到」仍要手動跑完整輪。

跑法：`python3 scripts/test_validate.py`（在 pack 目錄下），或 `python3 -m unittest`。
"""
import json
import re
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

    INTERNAL = "validator 內部錯誤"

    def run(self, *args, ci=False, script="plugins/pai-lenses/scripts/validate.py",
            allow_internal=False, env=None):
        """回傳 (rc, 合併後的輸出)。validate.py 把 error 印到 stdout（GitHub annotation）。

        `allow_internal`（#33 verify R13 修法後的 mutation 量測）：`main()` 逐閘門隔離之後，
        任何守衛被刪掉都只會變成一條「validator 內部錯誤」—— rc 仍是 1、也沒有 traceback，
        於是**每一條只斷言 rc / 沒 traceback / 有 ::error 的測試都分不出「守衛在」與「守衛沒了、
        由 gate() 兜住」**：83 靶跑出 8 個意外存活，全是這個形狀。gate() 是最後一張網，不是閘門；
        測試裡看到它就是缺了一道守衛，所以這裡**一律**視為失敗，要看它的那一條測試自己在
        行程內 monkeypatch（不走這裡）。這是類級的修法：不是在八條測試各補一句 assertNotIn。

        `ci` 是**必要的參數，不是方便**（#33 verify R8 CRITICAL）：`check_bumped` 的
        no-base 分支依序是 workflow_dispatch → **`GITHUB_ACTIONS != "true"` 本機** → CI
        的 fail-loud。先前這裡寫死 `GITHUB_ACTIONS=""`，於是**每一條測試都走本機分支**，
        後面兩道全部被吃掉 —— 整段 no-base fail-loud（R4 的頭號修正）可以換成無條件
        `return` 而 26 條測試全綠，而名義上守 workflow_dispatch 的那條測試實際命中的是
        本機分支，是**套套邏輯的綠燈**。正是本檔開頭批判的那種測試。"""
        r = subprocess.run(
            [sys.executable, str(self.repo / script), *args],
            cwd=self.repo, capture_output=True, text=True,
            env={**os.environ, "GITHUB_ACTIONS": "true" if ci else "", **(env or {})})
        out = r.stdout + r.stderr
        if not allow_internal and self.INTERNAL in out:
            raise AssertionError(
                f"某道閘門拋了例外、由 main() 的 gate() 兜住 —— 這代表缺了一道具名的守衛，"
                f"不是「沒 crash」：\n{out}")
        return r.returncode, out

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
        # 只斷言「撞名閘門沒有跑」分不出這道守衛與下面 except OSError 的「讀取失敗」（R13 後靶存活）：
        # 守衛的價值是**說對原因**——「找不到」而不是「讀取失敗：[Errno 2]」。
        out = self.assertRed(contains="找不到 plugins/parallel-ai-agents/references/builtin-lenses.csv")
        self.assertIn("這不是「沒有撞名」", out)

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
        # R14 全輪量測：只斷言「閘門沒有跑」分不出這道守衛與下游「bash 跑不起來（rc=127）」的訊息——
        # stderr 不再進 annotation 之後兩者只差在說對原因。守衛的價值就是**說對原因**（同 R13「catalog 缺檔」）。
        self.assertRed(contains="找不到 plugins/parallel-ai-agents/bin/pai-list-profiles")

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
        # R15 全輪量測：check_lens_dir_shape 自己的訊息與 main() 新加的「check_csvs 沒有跑（沒有合法 CSV）」都含
        # 「沒有任何合法」——只斷言那四個字分不出這道守衛。守衛的價值是**說對原因**（同 R13/R14 的兩個先例）。
        self.assertRed(contains="lenses/ 下沒有任何合法的 <profile>.csv")

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
                self.assertIn("不是物件", out, f"{label} 必須是 load_obj 的具名訊息：\n{out}")

    def test_marketplace_plugins_of_wrong_type_does_not_crash(self):
        self.fx.edit_json(".claude-plugin/marketplace.json",
                          lambda d: d.__setitem__("plugins", ["pai-lenses"]))
        out = self.assertRed(contains="`plugins` 的元素必須是物件")
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
        self.assertIn("不是物件", out, f"必須是 load_obj 的具名訊息：\n{out}")

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
        self.assertIn("不是物件", out, f"必須是 load_obj 的具名訊息：\n{out}")

    # ---- #33 verify R11 ----

    INJECT = "\n::stop-commands::zzz\n::error file=innocent.py,line=1::forged"

    def assertNoInjectedCommand(self, out):
        """輸出裡每一行凡 `TrimStart()` 後以 `::` 開頭者（runner 就是這樣判的），
        都必須是 validator 自己的 annotation 形狀，且不得帶注入標記。"""
        for line in out.splitlines():
            # V1（`##[cmd …]…`）：runner 用 IndexOf 定位，不 trim、不錨定行首 → 全行都不得出現（R12 DA-1）。
            self.assertNotIn("##[", line, f"V1 workflow command 進了 log：{line!r}\n{out}")
            t = line.lstrip()
            if not t.startswith("::"):
                continue
            self.assertFalse(t.startswith("::stop-commands::"), out)
            self.assertRegex(t, r"^::(error|warning|notice)(\s[^:]*)?::",
                             f"非 validator 形狀的 workflow command：{line!r}\n{out}")
            # runner 只把第二個 `::` 之前的部分當 command + properties；payload 以資料的
            # 身分出現在**訊息**裡是合法的（它已被 ⏎ 壓成同一行），出現在 head 才是偽造。
            head = t.split("::", 2)[1]
            self.assertNotIn("innocent.py", head, f"偽造的 annotation property：\n{out}")

    def test_manifest_version_cannot_inject_workflow_commands(self):
        """R11 #1：`check_version` 的成功路徑用裸 `print()` 印 version —— 整支程式的第 2 行
        就能是 `::stop-commands::`，之後所有 `::error::` 全被 runner 吞掉。"""
        self.fx.edit_json("plugins/pai-lenses/.claude-plugin/plugin.json",
                          lambda d: d.__setitem__("version", "0.2.0" + self.INJECT))
        rc, out = self.fx.run()
        self.assertNoInjectedCommand(out)

    def test_manifest_name_cannot_inject_on_the_green_path(self):
        """R11 #1（最嚴重的一條）：兩份 manifest 的 `name` 同時含換行 → 身分檢查通過、
        版本一致、lens 沒動 —— **rc=0 全綠**，而 log 帶 `::stop-commands::`。"""
        evil = "pai-lenses" + self.INJECT
        self.fx.edit_json("plugins/pai-lenses/.claude-plugin/plugin.json",
                          lambda d: d.__setitem__("name", evil))
        def rename_entry(d):
            for e in d["plugins"]:
                if e.get("name") == "pai-lenses":
                    e["name"] = evil
        self.fx.edit_json(".claude-plugin/marketplace.json", rename_entry)
        rc, out = self.fx.run()
        self.assertNoInjectedCommand(out)

    def test_output_boundary_covers_stdout_and_stderr(self):
        """R11 DA D2：runner 對 stderr 用**同一個** ActionCommandManager 解析，
        所以邊界必須同時包住兩條 stream；且要能處理跨多次 write() 的部分行。"""
        import io
        sys.path.insert(0, str(HERE))
        import validate as V
        buf = io.StringIO()
        w = V.LineSanitiser(buf)
        w.write("ok\n::stop-commands::x\n")
        w.write("  ::err")          # 縮排 + 分兩次寫完一行
        w.write("or::y\nplain::mid\n")
        self.assertEqual(buf.getvalue(), "ok\n∷stop-commands::x\n  ∷error::y\nplain::mid\n")
        # main() 前必須把兩條 stream 都換掉；emit() 走原始 stream 才印得出真的 annotation。
        old_out, old_err = sys.stdout, sys.stderr
        try:
            V.install_output_boundary()
            self.assertIsInstance(sys.stdout, V.LineSanitiser)
            self.assertIsInstance(sys.stderr, V.LineSanitiser)
            self.assertIs(V.RAW_OUT, old_out)
        finally:
            sys.stdout, sys.stderr = old_out, old_err
            V.RAW_OUT = None

    def test_emit_truncates_overlong_lines(self):
        """R11 #13：`emit()` 的截斷先前零測試（mutation 存活）。"""
        self.fx.edit_json("plugins/pai-lenses/.claude-plugin/plugin.json",
                          lambda d: d.__setitem__("version", "v" * 5000))
        rc, out = self.fx.run()
        self.assertEqual(rc, 1, out)
        cmds = [ln for ln in out.splitlines() if ln.startswith("::")]
        self.assertTrue(any(ln.endswith("…（截斷）") for ln in cmds), out)
        self.assertFalse(any(len(ln) > 4200 for ln in cmds), "超長的 annotation 沒被截斷")

    def test_duplicate_entry_name_with_remote_source_is_error(self):
        """R11 #2：`entry_names.add()` 在所有 `continue` 之後 —— 第二條同名 entry 只要
        source 是遠端，撞名完全不報、rc=0。情境正是「舊的遠端 pai-lenses entry 沒刪乾淨」。"""
        self.fx.add_entry("pai-lenses", "github:someone/pai-lenses")
        self.assertRed(contains="重複", msg="遠端來源的同名 entry 也要報撞名")

    def test_clean_run_does_not_claim_a_rename(self):
        """R11 #4：`_find_pack_at` 在沒改名時回傳現路徑，於是每個沒碰 lens 的 PR 都印
        「（偵測到純目錄改名，內容零變動）」—— 綠燈路徑上一句永遠為假的話。"""
        base = self.fx.commit("base")
        (self.fx.repo / "README.md").write_text("unrelated\n", encoding="utf-8")
        self.fx.commit("無關檔案")
        for ev in ("push", "pull_request"):
            out = self.assertGreen(("--base", base, "--event", ev), msg=ev)
            self.assertNotIn("純目錄改名", out, f"沒有改名不得宣稱偵測到改名（{ev}）：\n{out}")

    def test_rename_plus_small_edit_is_still_caught(self):
        """R11 #5：既有的「改名 + 改內容」fixture 整檔覆寫，git 判成 A/D 而非 R，沒踩到
        `R100` 那條分支。這裡只 append 一行（git 判 R09x），把放寬方向鎖住。"""
        base = self.fx.commit("base")
        git(self.fx.repo, "mv", "plugins/pai-lenses", "plugins/lens-pack")
        self.fx.set_entry("pai-lenses", source="./plugins/lens-pack")
        csv_path = self.fx.repo / "plugins/lens-pack/lenses/code.csv"
        csv_path.write_text(csv_path.read_text(encoding="utf-8") + 'added,"append one lens"\n',
                            encoding="utf-8")
        self.fx.commit("改名 + 追加一條")
        # 兩個路徑都給 git，rename detection 才配得起來（validate.py 自己也是這樣呼叫的）。
        status = git(self.fx.repo, "diff", "--name-status", "-M", base, "HEAD",
                     "--", "plugins/pai-lenses/lenses", "plugins/lens-pack/lenses").stdout
        self.assertRegex(status, r"^R0\d\d\t", f"fixture 必須逼出 R0xx：\n{status}")
        rc, out = self.fx.run("--base", base, "--event", "push",
                              script="plugins/lens-pack/scripts/validate.py")
        self.assertEqual(rc, 1, f"改名時追加 lens 仍要擋：\n{out}")
        self.assertIn("版本沒有增加", out)

    def test_description_version_prefix_must_match_version(self):
        """R11 #3：rebase 後 version 改 2.24.0、description 仍寫 `v2.23.0:`，而兩份一起錯時
        既有的 description-drift 閘門靜默。description 若帶 `v<semver>:` 前綴，最新那個
        必須等於 version 欄。"""
        self.fx.edit_json("plugins/pai-lenses/.claude-plugin/plugin.json",
                          lambda d: d.__setitem__("description", "v9.9.9: 假的版本說明"))
        self.fx.set_entry("pai-lenses", description="v9.9.9: 假的版本說明")
        out = self.assertGreen(msg="只 warning 不 error")
        self.assertIn("::warning", out)
        self.assertIn("v9.9.9", out)
        self.assertIn("description", out)

    def test_comma_in_filename_cannot_forge_annotation_properties(self):
        """R11 #6：runner 用 `,` 切 property、`=` 切 key/value；`file=` 位置從未消毒。
        檔名 `x,line=99,title=CI PASSED.CSV` 會被渲染成第 99 行、標題「CI PASSED」。"""
        (self.fx.repo / "plugins/pai-lenses/lenses" / "x,line=99,col=1,title=CI PASSED.CSV").write_text(
            'key,focus\nk,"f"\n', encoding="utf-8")
        rc, out = self.fx.run()
        self.assertEqual(rc, 1, out)
        for line in out.splitlines():
            if line.startswith("::"):
                head = line.split("::", 2)[1]      # `error file=…,line=…`
                # 照 runner 的切法：`,` 切 property、第一個 `=` 切 key/value。
                keys = [kv.split("=", 1)[0] for kv in head.split(" ", 1)[1].split(",")] \
                    if " " in head else []
                self.assertNotIn("line", keys, f"property 被檔名偽造：{line}")
                self.assertNotIn("title", keys, f"property 被檔名偽造：{line}")

    def test_lens_annotation_file_path_is_repo_relative(self):
        """R11 #7：`file=lenses/code.csv` 是相對 pack 根 —— 併回後 repo 根沒有這個檔，
        annotation 貼不上 PR diff。runner 只會自動轉換 workspace 底下的絕對路徑。"""
        (self.fx.repo / "plugins/pai-lenses/lenses/Upper.CSV").write_text(
            'key,focus\nk,"f"\n', encoding="utf-8")
        out = self.assertRed(contains="副檔名必須是小寫")
        self.assertIn("file=plugins/pai-lenses/lenses/Upper.CSV::", out)

    def test_entry_without_source_field_says_fix_the_entry(self):
        """R11 #8：`culprit is not None` 把「沒有這個名字的 entry」與「有名字但 source
        缺席／null」混為一談 —— 最常見的寫錯（忘了寫 source）仍被導向「再加一條 entry」。"""
        def drop_source(d):
            for e in d["plugins"]:
                if e.get("name") == "pai-lenses":
                    e.pop("source", None)
        self.fx.edit_json(".claude-plugin/marketplace.json", drop_source)
        out = self.assertRed(contains="要修的是那條 entry 的 source")
        self.assertNotIn("沒有指向它的 entry", out)

    def test_reverse_check_does_not_read_plugin_json_outside_repo(self):
        """R11 #12：`check_marketplace_sync` 的反向 glob 跟隨 symlink —— 五處 `_inside`
        硬化漏了第六處。"""
        outside = self.fx.dir / "evilplug"
        (outside / ".claude-plugin").mkdir(parents=True)
        (outside / ".claude-plugin/plugin.json").write_text(
            '{"name":"evil","version":"1.0.0","description":"SECRET-OUTSIDE-DESC"}\n',
            encoding="utf-8")
        (self.fx.repo / "plugins/evil").symlink_to(outside)
        out = self.assertRed(contains="落在 repo 外")
        self.assertNotIn("SECRET-OUTSIDE-DESC", out)
        self.assertNotIn("plugins/evil 有 plugin.json", out, "不可先讀了才報")

    def test_lens_file_rename_across_profiles_is_a_change_not_a_pure_rename(self):
        """R11 mutation 存活（git 分支）：`lenses/code.csv → lenses/academic.csv` 是同一 pack 內的
        R100 —— 先前 (a) `_find_pack_at` 的多數決把 pack 自己投成「舊路徑」、印出假的
        「純目錄改名」；(b) `R100` 被無條件當成純改名 —— 但檔名就是 profile，lens 整批從 code
        搬到 academic 是**真的變更**，使用者 /plugin update 收不到卻沒 bump。"""
        base = self.fx.commit("base")
        git(self.fx.repo, "mv", "plugins/pai-lenses/lenses/code.csv",
            "plugins/pai-lenses/lenses/academic.csv")
        self.fx.commit("lens 檔改名到另一個 profile")
        rc, out = self.fx.run("--base", base, "--event", "push")
        self.assertNotIn("純目錄改名", out, f"pack 目錄沒動，不得宣稱目錄改名：\n{out}")
        self.assertEqual(rc, 1, f"跨 profile 的 lens 搬移要 bump：\n{out}")
        self.assertIn("版本沒有增加", out)

    # ---- #33 verify R12 ----

    SEPARATORS = ("\n", "\r\n", "\r", "\n\v", "\n\f", "\n\x85", "\n ", "\n ", "\n\t", "\n ")

    def test_output_boundary_uses_the_runners_line_definition(self):
        """R12 #1（三個 lens + DA）：R11 的 LineSanitiser 用 Python `splitlines()` 切段（8 種行界），
        卻用 `endswith(("\\n","\\r"))` 判行首。`\\v` `\\f` `\\x85` U+2028 U+2029 讓 `_at_line_start`
        在實體行中途歸零，下一段的 `::` 不經消毒；而 .NET `TrimStart()` 會吃掉那些字元 →
        runner 眼裡就是行首的 command。R11 的兩條測試只守 `\\n` 這一個字元。"""
        import io
        sys.path.insert(0, str(HERE))
        import validate as V
        for sep in self.SEPARATORS:
            with self.subTest(sep=repr(sep)):
                buf = io.StringIO()
                V.LineSanitiser(buf).write(f"version = 1.0.0{sep}::stop-commands::x\n")
                for line in buf.getvalue().split("\n"):
                    self.assertFalse(line.lstrip().startswith("::"),
                                     f"分隔符 {sep!r} 之後的 :: 沒被中和：{buf.getvalue()!r}")

    def test_manifest_injection_is_blocked_for_every_separator(self):
        """R12 #1 端到端：把 INJECT 的分隔符換成封閉列舉的每一種，version 與 name 兩條路徑都要守住。"""
        for sep in self.SEPARATORS:
            with self.subTest(sep=repr(sep)):
                fx = Fixture(); self.addCleanup(fx.cleanup)
                payload = sep + "::stop-commands::zzz" + sep + "::error file=innocent.py,line=1::forged"
                fx.edit_json("plugins/pai-lenses/.claude-plugin/plugin.json",
                             lambda d: d.__setitem__("version", "0.2.0" + payload))
                rc, out = fx.run()
                self.assertNoInjectedCommand(out)
                fx2 = Fixture(); self.addCleanup(fx2.cleanup)
                evil = "pai-lenses" + payload
                fx2.edit_json("plugins/pai-lenses/.claude-plugin/plugin.json",
                              lambda d: d.__setitem__("name", evil))
                def rename_entry(d):
                    for e in d["plugins"]:
                        if e.get("name") == "pai-lenses":
                            e["name"] = evil
                fx2.edit_json(".claude-plugin/marketplace.json", rename_entry)
                rc, out = fx2.run()
                self.assertNoInjectedCommand(out)

    def test_reverse_check_survives_hostile_plugin_json(self):
        """R12（security #2）：反向 glob 是唯一沒走 load_obj 的 JSON 讀取點。`{"name":[]}` →
        `TypeError: unhashable type`；非 UTF-8 → `UnicodeDecodeError`。兩者都是裸 traceback、
        零 annotation，已累積的 errs 全部消失。"""
        for label, content in (("name 是 list", b'{"name":[],"version":"1.0.0"}\n'),
                               ("非 UTF-8", b'\xff\xfe{"name":"x"}\n')):
            with self.subTest(case=label):
                fx = Fixture(); self.addCleanup(fx.cleanup)
                d = fx.repo / "plugins/hostile/.claude-plugin"; d.mkdir(parents=True)
                (d / "plugin.json").write_bytes(content)
                fx.write_lenses("key,focus\n")          # 一條真的 error，看它有沒有被吃掉
                rc, out = fx.run()
                self.assertNotIn("Traceback", out, out)
                self.assertEqual(rc, 1, out)
                self.assertIn("::error", out, "其他 finding 不得隨 crash 消失")

    def test_directory_name_cannot_forge_annotation_properties(self):
        """R12（logic L2）：R11 #6 的轉義只落在 lens CSV 兩個站點，manifest 側 24 個 `file=`
        仍是裸路徑——目錄名 `plugins/evil,line=1,title=CI PASSED/` 一樣能偽造 property。"""
        d = self.fx.repo / "plugins/evil,line=1,col=1,title=CI PASSED/.claude-plugin"
        d.mkdir(parents=True)
        (d / "plugin.json").write_text("{not json", encoding="utf-8")
        self.fx.add_entry("evil", "./plugins/evil,line=1,col=1,title=CI PASSED")
        rc, out = self.fx.run()
        self.assertEqual(rc, 1, out)
        for line in out.splitlines():
            if line.startswith("::") and " " in line.split("::", 2)[1]:
                head = line.split("::", 2)[1]
                keys = [kv.split("=", 1)[0] for kv in head.split(" ", 1)[1].split(",")]
                self.assertNotIn("line", keys, f"property 被目錄名偽造：{line}")
                self.assertNotIn("title", keys, f"property 被目錄名偽造：{line}")

    def test_source_outside_plugins_dir_with_symlinked_claude_plugin_is_blocked(self):
        """R12（requirements R12-1）：「containment（只判目錄層）」的靶存活被寫成 equivalent，
        理由是反向 glob 會接住——但反向 glob 只枚舉 plugins/*，source 指到 docs/ 時它看不到。
        這個 fixture 讓那個靶轉紅。"""
        outside = self.fx.dir / "evilplug"
        (outside / ".claude-plugin").mkdir(parents=True)
        (outside / ".claude-plugin/plugin.json").write_text(
            '{"name":"evil","version":"9.9.9"}\n', encoding="utf-8")
        (self.fx.repo / "docs/evil").mkdir(parents=True)
        (self.fx.repo / "docs/evil/.claude-plugin").symlink_to(outside / ".claude-plugin")
        self.fx.add_entry("evil", "./docs/evil")
        out = self.assertRed(contains="落在 repo 外")
        self.assertNotIn("evil 9.9.9 ✓", out, "不得讀了 repo 外的 plugin.json 還印綠")

    def test_description_prefix_gate_reads_the_first_version_as_the_latest(self):
        """R12（logic L4）：「第一個 v<semver>: 就是最新版」是慣例，先前沒有規格也沒有測試——
        把 re.search 換成取最後一個 match，全套仍綠。這裡把兩個方向都釘住。"""
        ver = json.loads((self.fx.repo / "plugins/pai-lenses/.claude-plugin/plugin.json")
                         .read_text(encoding="utf-8"))["version"]
        old_first = f"v0.0.1: 舊的在前。v{ver}: 新的在後"
        new_first = f"v{ver}: 新的在前。v0.0.1: 舊的在後"
        for desc, expect_warn in ((old_first, True), (new_first, False)):
            with self.subTest(desc=desc):
                fx = Fixture(); self.addCleanup(fx.cleanup)
                fx.edit_json("plugins/pai-lenses/.claude-plugin/plugin.json",
                             lambda d: d.__setitem__("description", desc))
                fx.set_entry("pai-lenses", description=desc)
                rc, out = fx.run()
                self.assertEqual(rc, 0, out)
                self.assertEqual("description 最新一段標示" in out, expect_warn, out)

    def test_lister_symlink_outside_repo_is_not_executed(self):
        """R12（security LOW）：`bin/pai-list-profiles` 只有 is_file() 就被 bash 執行——
        containment 的第七處。"""
        outside = self.fx.dir / "evil.sh"
        outside.write_text("#!/bin/bash\necho code\n", encoding="utf-8")
        lister = self.fx.repo / "plugins/parallel-ai-agents/bin/pai-list-profiles"
        lister.unlink(); lister.symlink_to(outside)
        self.assertRed(contains="落在 repo 外")

    V1_PAYLOADS = (
        "pai-lenses ##[stop-commands]zzz ##[error file=innocent.py,line=1]forged",   # 單行、零換行
        ">>>   ##[do-something k1=v1;]msg",                                            # runner 自己的 L0 測試輸入
        "x\t##[error file=innocent.py]FORGED",
    )

    def test_v1_workflow_command_syntax_is_neutralised_everywhere(self):
        """R12 DA-1：runner 對每一行依序試兩個 parser。V1 `##[…]` 用 IndexOf 定位——不 trim、不錨定
        行首、不需要換行。R11/R12 前半的 LineSanitiser / wc / emit 沒有一個碰它（全樹 grep 零命中）。"""
        import io
        sys.path.insert(0, str(HERE))
        import validate as V
        for payload in self.V1_PAYLOADS:
            with self.subTest(payload=payload):
                buf = io.StringIO()
                V.LineSanitiser(buf).write(payload + "\n")
                self.assertNotIn("##[", buf.getvalue(), buf.getvalue())
                self.assertNotIn("##[", V.wc(payload))
        # 端到端、rc=0 綠燈路徑：兩份 manifest 的 name 同時含 V1 payload
        evil = self.V1_PAYLOADS[0]
        self.fx.edit_json("plugins/pai-lenses/.claude-plugin/plugin.json",
                          lambda d: d.__setitem__("name", evil))
        def rename_entry(d):
            for e in d["plugins"]:
                if e.get("name") == "pai-lenses":
                    e["name"] = evil
        self.fx.edit_json(".claude-plugin/marketplace.json", rename_entry)
        rc, out = self.fx.run()
        self.assertNoInjectedCommand(out)
        # emit() 那一路（errs 內含 payload）也要中和
        fx2 = Fixture(); self.addCleanup(fx2.cleanup)
        fx2.edit_json("plugins/pai-lenses/.claude-plugin/plugin.json",
                      lambda d: d.__setitem__("version", "0.2.0 " + evil))
        rc, out = fx2.run()
        self.assertNoInjectedCommand(out)

    def test_output_boundary_buffers_partial_lines(self):
        """R12 DA-3：`::` 被切在兩次 write() 中間時（`write("x\\n:")` + `write(":stop-commands::…")`），
        只記 _at_line_start 的實作看不到 `::`。改成緩衝未完成的一行、到行界才判。"""
        import io
        sys.path.insert(0, str(HERE))
        import validate as V
        buf = io.StringIO(); w = V.LineSanitiser(buf)
        w.write("x\n:"); w.write(":stop-commands::H\n")
        self.assertEqual(buf.getvalue(), "x\n∷stop-commands::H\n")
        buf2 = io.StringIO(); w2 = V.LineSanitiser(buf2)
        w2.write("tail without newline ::x"); w2.flush()
        self.assertIn("tail without newline ::x", buf2.getvalue(), "flush 時未完成的一行也要寫出")

    def test_emit_truncation_keeps_the_command_head_intact(self):
        """R12 DA-1（推論，補成事實）：emit() 在 4000 字截斷，若 `file=` 的值把第二個 `::` 推過 4000，
        TryParseV2 找不到第二個 `::` 就 return false，該行落到 V1 parser。截斷只能截訊息。
        （檔案系統做不出 4000 字的路徑，所以直接餵 emit()。）"""
        import io
        sys.path.insert(0, str(HERE))
        import validate as V
        buf = io.StringIO(); V.RAW_OUT = buf
        try:
            V.emit("::error file=" + "a" * 5000 + "::" + "m" * 5000 + " ##[error]x")
        finally:
            V.RAW_OUT = None
        line = buf.getvalue().rstrip("\n")
        self.assertTrue(line.startswith("::error file=aaaa"), line[:60])
        self.assertGreater(line.find("::", 2), 0, "命令頭（第二個 ::）被截掉了")
        self.assertIn("…（截斷）", line)
        self.assertNotIn("##[", line)

    # ---- #33 verify R13 ----

    def test_non_utf8_pack_manifest_never_crashes_any_gate(self):
        """R13 security S1：R12 修法宣稱「反向 glob 是唯一沒走 load_obj 的 JSON 讀取點」——假的。
        非 UTF-8 的 pack plugin.json 還會在 check_bumped 的 pack_name 讀取（except 少列
        UnicodeDecodeError）與 `git show`（subprocess text=True 解碼）炸成裸 traceback，
        已累積的 annotation 全部消失、後面的閘門整段不跑。"""
        base = self.fx.commit("base")
        pj = self.fx.repo / "plugins/pai-lenses/.claude-plugin/plugin.json"
        pj.write_bytes(b'\xff\xfe{"name":"pai-lenses","version":"0.2.0"}\n')
        self.fx.write_lenses("key,focus\n")           # 一條真的 error，看它有沒有被吃掉；也讓 bump 檢查走到 git show
        self.fx.commit("非 UTF-8 的 manifest + lens 變更")
        for args in ((), ("--base", base, "--event", "push")):
            with self.subTest(args=args):
                rc, out = self.fx.run(*args)
                self.assertNotIn("Traceback", out, out)
                self.assertEqual(rc, 1, out)
                self.assertIn("解析出 0 條 lens", out, "後面的閘門（check_csvs）必須仍然跑到")

    def test_pack_own_claude_plugin_symlink_is_not_read_by_check_version(self):
        """R13 logic N1：containment 的第八、九處——pack 自己的 .claude-plugin 是 symlink 時，
        check_version 會印出 repo 外檔案的 version，而同一次輸出的下兩行卻說「拒絕讀取」。"""
        outside = self.fx.dir / "outside-cp"; outside.mkdir()
        (outside / "plugin.json").write_text('{"name":"pai-lenses","version":"9.9.9"}\n', encoding="utf-8")
        cp = self.fx.repo / "plugins/pai-lenses/.claude-plugin"
        shutil.rmtree(cp); cp.symlink_to(outside)
        out = self.assertRed(contains="落在 repo 外")
        self.assertNotIn("version = 9.9.9", out, "repo 外的 version 不得被印出")

    def test_description_prefix_regex_survives_cjk_adjacency(self):
        """R13 logic N2：`\\bv` 在 CJK 相黏時（「補齊v0.0.1:」）不成立，閘門跳過真正最前面的版號。"""
        ver = json.loads((self.fx.repo / "plugins/pai-lenses/.claude-plugin/plugin.json")
                         .read_text(encoding="utf-8"))["version"]
        desc = f"補齊v0.0.1: 舊的黏在前面。v{ver}: 新的在後"
        self.fx.edit_json("plugins/pai-lenses/.claude-plugin/plugin.json",
                          lambda d: d.__setitem__("description", desc))
        self.fx.set_entry("pai-lenses", description=desc)
        out = self.assertGreen()
        self.assertIn("description 最新一段標示 v0.0.1", out, out)

    def test_output_boundary_flush_neutralises_pending_line(self):
        """R13 logic N5：flush() 時殘餘那一行也要經同一道判定（靶先前存活）。"""
        import io
        sys.path.insert(0, str(HERE))
        import validate as V
        buf = io.StringIO(); w = V.LineSanitiser(buf)
        w.write("::stop-commands::x ##[error]y"); w.flush()
        self.assertEqual(buf.getvalue(), "∷stop-commands::x ##⟦error]y")

    def test_harness_symlink_outside_repo_is_not_evaluated_or_leaked(self):
        """R13 requirements R13-4：containment 補到 lister（執行點），沒補到它求值的輸入
        （workflows/ensemble-workflow.js）。symlink 到 repo 外的檔案會被 node 求值，SyntaxError
        的 code frame 把該檔內容經 stderr → errs → annotation 印出來。"""
        outside = self.fx.dir / "outside.mjs"
        outside.write_text("TOP-SECRET-HARNESS-LINE = 42 !!!\n", encoding="utf-8")
        h = self.fx.repo / "plugins/parallel-ai-agents/workflows/ensemble-workflow.js"
        h.unlink(); h.symlink_to(outside)
        out = self.assertRed(contains="落在 repo 外")
        self.assertNotIn("TOP-SECRET-HARNESS-LINE", out, "repo 外檔案內容不得進 annotation")

    def test_main_drains_accumulated_errors_even_if_a_gate_crashes(self):
        """R13 DA-1：缺陷類的根因不是「哪個 except 漏了」，而是 main() 把所有 annotation 留到最後才印——
        任何一個閘門拋例外，已累積的 errs 全部消失，後面的閘門也不跑。這是同一結構第五次發作。"""
        import io
        sys.path.insert(0, str(HERE))
        import validate as V
        buf = io.StringIO()
        orig_main_argv, orig_bumped, orig_raw = sys.argv, V.check_bumped, V.RAW_OUT
        def boom(*a, **k):
            raise RuntimeError("boom ::stop-commands::x")
        import contextlib
        plain = io.StringIO()
        try:
            sys.argv = ["validate.py"]
            V.check_bumped = boom
            V.RAW_OUT = buf
            with contextlib.redirect_stdout(plain):     # print() 走 sys.stdout（會被 LineSanitiser 包住）
                rc = V.main()
        finally:
            sys.argv, V.check_bumped, V.RAW_OUT = orig_main_argv, orig_bumped, orig_raw
        out = buf.getvalue() + plain.getvalue()
        self.assertEqual(rc, 1, out)
        self.assertIn("validator 內部錯誤", out, out)
        self.assertIn("check_bumped", out, "要指名是哪道閘門沒跑完")
        self.assertNotIn("::stop-commands::", out.split("::", 2)[-1] if False else "\n".join(
            l for l in out.splitlines() if l.lstrip().startswith("::stop-commands")), "例外訊息也要消毒")
        self.assertIn("條 lens ✓", out, "後面的閘門（check_csvs）仍要跑到")

    def test_output_boundary_writelines_is_sanitised(self):
        """R13 DA-3：`__getattr__` 把 writelines 透傳到底層 stream，兩套語法原樣落地。"""
        import io
        sys.path.insert(0, str(HERE))
        import validate as V
        buf = io.StringIO(); w = V.LineSanitiser(buf)
        w.writelines(["::stop-commands::zzz\n", "##[error file=a]F\n"]); w.flush()
        self.assertEqual(buf.getvalue(), "∷stop-commands::zzz\n##⟦error file=a]F\n")

    def test_emit_recognises_a_command_head_after_leading_whitespace(self):
        """R13 DA-12：emit() 用 startswith("::") 判 head、runner 用 TrimStart()——同一個概念兩套定義。"""
        import io
        sys.path.insert(0, str(HERE))
        import validate as V
        buf = io.StringIO(); V.RAW_OUT = buf
        try:
            V.emit("  ::error file=x::" + "A" * 5000)
        finally:
            V.RAW_OUT = None
        line = buf.getvalue().rstrip("\n")
        self.assertTrue(line.startswith("::error file=x::"), line[:40])
        self.assertIn("…（截斷）", line)

    # ---- #33 verify R14 ----

    def _unlink_root_marketplace(self):
        (self.fx.repo / ".claude-plugin" / "marketplace.json").rename(
            self.fx.repo / ".claude-plugin" / "marketplace.json.moved")

    def test_missing_root_marketplace_in_ci_is_fail_loud_not_five_silent_skips(self):
        """R14 logic L-1：fork 把 `.claude-plugin/marketplace.json` 改名，`repo_root()` 回 None，
        marketplace-sync／bump／lenses containment／撞名／profile 名**五道閘門**一次全部只剩 note、
        rc=0，外加一則肯定式假 warning（「沒有 ensemble-code-review 這支 skill」）。
        同檔的 no-base 路徑早有「本機 note ／ CI errs」分流（R4/R5），這裡沒有。"""
        self._unlink_root_marketplace()
        out = self.assertRed(ci=True, contains="道閘門都沒有跑")
        self.assertIn("marketplace.json", out)
        self.assertNotIn("沒有 ensemble-code-review", out, "找不到 repo 時不得印那句假 warning")

    def test_missing_root_marketplace_locally_notes_once_without_false_warning(self):
        """同上，本機分支：可以只 note，但那句假 warning 一樣不得出現。"""
        self._unlink_root_marketplace()
        out = self.assertGreen()
        self.assertIn("道閘門都沒有跑", out)
        self.assertNotIn("沒有 ensemble-code-review", out)

    def test_lenses_containment_holds_even_without_monorepo_root(self):
        """R14 logic L-1 的第二段：`repo_root()` 為 None 時 `lenses/` 目錄的 containment 整段跳過，
        R9 標 HIGH 的 symlink 外洩就回來了。邊界退回 pack 自己（`root`），與 check_version 同形。"""
        self._unlink_root_marketplace()
        outside = self.fx.dir / "outside-lenses"; outside.mkdir()
        (outside / "leak.csv").write_text("SECRET-OUTSIDE-LENS-HEADER\n", encoding="utf-8")
        lenses = self.fx.repo / "plugins/pai-lenses/lenses"
        shutil.rmtree(lenses); lenses.symlink_to(outside, target_is_directory=True)
        out = self.assertRed(contains="落在 repo 外")
        self.assertNotIn("SECRET-OUTSIDE-LENS-HEADER", out)

    def test_root_marketplace_symlink_outside_repo_is_rejected_not_read(self):
        """R14 logic L-2：containment 的第十處——repo 根的 `marketplace.json` 直接 `load_obj`，
        repo 外內容被讀、驅動版本閘門、原樣進 `::warning`、rc=0。"""
        outside = self.fx.dir / "outside-cp"; outside.mkdir()
        (outside / "marketplace.json").write_text(json.dumps({"name": "x", "plugins": [
            {"name": "OUTSIDE-CONTENT-REACHED-CI", "source": "weird", "version": "1.0.0"}]}),
            encoding="utf-8")
        cp = self.fx.repo / ".claude-plugin"
        shutil.rmtree(cp); cp.symlink_to(outside, target_is_directory=True)
        out = self.assertRed(contains="落在 repo 外")
        self.assertNotIn("OUTSIDE-CONTENT-REACHED-CI", out)

    def test_skill_md_outside_repo_is_not_read_by_collector_wiring(self):
        """R14 logic L-2 第 11 處：`collector_wiring` 讀 `skills/ensemble-<profile>-review/SKILL.md`
        時沒有 containment。symlink 到 repo 外時要當成「沒有這支 skill 可看」而不是讀它。"""
        outside = self.fx.dir / "outside-skill"; outside.mkdir()
        (outside / "SKILL.md").write_text("bin/pai-collect-lens-layers code\n", encoding="utf-8")
        d = self.fx.repo / "plugins/parallel-ai-agents/skills/ensemble-code-review"
        shutil.rmtree(d); d.symlink_to(outside, target_is_directory=True)
        out = self.assertGreen()
        self.assertIn("落在 repo 外", out, "要說出來，不能靜默當成已接線")

    def test_pai_harness_env_cannot_redirect_what_gets_evaluated(self):
        """R14 regression E-2 / logic L-7：validate.py 對預設 harness 路徑做 containment，卻讓
        lister 繼承整個環境；`PAI_HARNESS` 一設，檢查的檔與求值的檔就是兩個（逐字是 R6 修過的缺陷）。"""
        outside = self.fx.dir / "outside.mjs"
        outside.write_text("this is not javascript ( { EXFIL-HARNESS-CANARY\n", encoding="utf-8")
        rc, out = self.fx.run(env={"PAI_HARNESS": str(outside)})
        self.assertEqual(rc, 0, out)
        self.assertNotIn("EXFIL-HARNESS-CANARY", out)
        self.assertNotIn("無法取得 PROFILES", out, "求值的必須是 repo 內那份 harness")

    def test_harness_evaluation_stderr_never_enters_annotation(self):
        """R14 security S1：路徑 containment 擋不住 repo 內合法 harness 去 `import` repo 外的檔——
        node 的 code frame 把被 import 的檔案內容經 stderr → annotation 印出。類級修法：
        harness 求值的 stderr **一律不進 annotation**（只留固定訊息 + rc），內容再也沒有管道。"""
        outside = self.fx.dir / "leak.mjs"
        outside.write_text("TOP-SECRET-CANARY-9f3a syntax error here (((\n", encoding="utf-8")
        h = self.fx.repo / "plugins/parallel-ai-agents/workflows/ensemble-workflow.js"
        h.write_text(f"import '{outside}'\n" + h.read_text(encoding="utf-8"), encoding="utf-8")
        out = self.assertRed(contains="無法取得 PROFILES")
        self.assertNotIn("TOP-SECRET-CANARY-9f3a", out)
        self.assertNotIn("leak.mjs", out, "連路徑都不該進 annotation——那是 stderr 的內容")

    def test_in_repo_broken_harness_leaks_nothing_either(self):
        """R14 logic L-6：R13 #2 的另一半（stderr 走 wc()）零測試、零靶。現在改成 stderr 不進
        annotation，這條測試釘住它：壞掉的 in-repo harness 的 `##[…]` 與內容都不得出現。"""
        h = self.fx.repo / "plugins/parallel-ai-agents/workflows/ensemble-workflow.js"
        h.write_text('const LEAK = "##[error]REGEN_LEAK" ) syntax error here\n'
                     + h.read_text(encoding="utf-8"), encoding="utf-8")
        out = self.assertRed(contains="無法取得 PROFILES")
        self.assertNotIn("##[", out); self.assertNotIn("REGEN_LEAK", out)

    def test_gate_dependency_is_named_when_lens_dir_shape_crashes(self):
        """R14 logic L-3(a)：`check_lens_dir_shape` 拋例外 → `files` 為 None → `check_csvs` 整支不跑，
        卻沒有任何一句話說它沒跑，而「其餘閘門的結果仍在下面」在這條路徑上是假的。"""
        import io, contextlib
        sys.path.insert(0, str(HERE))
        import validate as V
        buf = io.StringIO(); plain = io.StringIO()
        orig = sys.argv, V.check_lens_dir_shape, V.RAW_OUT
        def boom(*a, **k): raise RuntimeError("boom")
        try:
            sys.argv = ["validate.py"]; V.check_lens_dir_shape = boom; V.RAW_OUT = buf
            with contextlib.redirect_stdout(plain):
                rc = V.main()
        finally:
            sys.argv, V.check_lens_dir_shape, V.RAW_OUT = orig
        out = buf.getvalue() + plain.getvalue()
        self.assertEqual(rc, 1, out)
        self.assertIn("check_csvs 沒有跑（前一道閘門 check_lens_dir_shape 未跑完", out,
                      "要指名 check_csvs 沒有跑，且說對原因（R15 全輪：`elif files is None` 被關掉會落到 `[]` 的訊息）")
        self.assertNotIn("沒有任何合法的 CSV 檔", out, "None 與 [] 是兩個原因，不得混")
        self.assertNotIn("其餘閘門的結果仍在下面", out, "這句在相依路徑上是假的，不得再印")

    def test_drain_survives_an_emit_failure(self):
        """R14 logic L-3(b)：`for e in errs: emit(e)` 不在任何 gate 內——emit() 一拋（surrogate、
        strict locale），已累積的 annotation 全部消失 + 裸 traceback，正是 gate() 存在的理由。"""
        import io, contextlib
        sys.path.insert(0, str(HERE))
        import validate as V
        class Strict(io.StringIO):
            def write(self, t):
                t.encode("utf-8")            # surrogate → UnicodeEncodeError（模擬 strict stdout）
                return super().write(t)
        buf = Strict(); plain = io.StringIO()
        orig = sys.argv, V.check_bumped, V.RAW_OUT
        def bad(root, errs, base, event=None):
            errs.append("::error::first \udcff bad"); errs.append("::error::second fine")
        try:
            sys.argv = ["validate.py"]; V.check_bumped = bad; V.RAW_OUT = buf
            with contextlib.redirect_stdout(plain):
                rc = V.main()
        finally:
            sys.argv, V.check_bumped, V.RAW_OUT = orig
        out = buf.getvalue() + plain.getvalue()
        self.assertEqual(rc, 1, out)
        self.assertIn("second fine", out, "後面的 annotation 不得因為前一條印不出來而消失")
        self.assertIn("first", out, "印不出來的那條也要以退化形式留下痕跡")

    def test_pack_name_containment_keeps_outside_name_out_of_log(self):
        """R14 requirements F3：EXPECTED_SURVIVE 第四條理由是假的——`check_bumped` 會
        `print(pack_name)`（「找不到名為 X 的 pack」），守衛拿掉時 repo 外 symlink 的 name 就進 log。
        它不是 equivalent mutant，是一道沒有測試網的真守衛；這條測試就是那張網。"""
        # R14 DA 更正：committed symlink 在 `git show HEAD:plugin.json` 就 return（blob 是 symlink 目標、不是 JSON），
        # 到不了那行 print；只有 **dirty worktree**（HEAD 有真檔、工作樹是 symlink）才到得了——CI 的 checkout
        # 產不出這個狀態，所以這是本機情境的守衛。測試就用那個形狀，讓靶不再是「沒測試網的 equivalent」。
        pack = self.fx.repo / "plugins/pai-lenses"
        parked = self.fx.dir / "parked-pack"; shutil.move(str(pack), str(parked))
        base = self.fx.commit("base：還沒有 pack")
        shutil.move(str(parked), str(pack))
        self.fx.commit("新增整個 pack（manifest 是真檔）")
        outside = self.fx.dir / "outside-cp2"; outside.mkdir()
        (outside / "plugin.json").write_text('{"name":"EXFIL-CANARY-QQ7","version":"0.2.0"}\n', encoding="utf-8")
        cp = pack / ".claude-plugin"; shutil.rmtree(cp); cp.symlink_to(outside, target_is_directory=True)
        rc, out = self.fx.run("--base", base, "--event", "push")
        self.assertIn("找不到名為", out, "要走到那行 print 才算測到守衛")
        self.assertNotIn("EXFIL-CANARY-QQ7", out, out)

    def test_every_filesystem_read_site_is_enumerated(self):
        """R14 logic L-2 / security S1 → R15 L-1 / F1 / F4 / S-1：R14 用**六種字面拼法的 regex** 當偵測器，
        四個 lens 各自注入 `open(`／`glob`／`Popen`／`os.listdir`／`check_output`／`shutil.copy` 全部靜默穿過，
        而 `validate.py` 反向檢查的 `glob(` 本來就是表外站點。偵測改走 AST：任何 Call 只要呼叫名落在
        `READ_CALLS`（封閉列舉，寫在 validate.py 旁邊）或 base 是 `subprocess`／`shutil`／`os` 的 spawn／walk
        家族，就必須帶 `# READ-SITE k/N`（同一行或前一行），且 N == len(READ_SITES) == 標記數。
        純 metadata 述詞（is_file/is_dir/exists/stat/resolve/relative_to）**不在列舉內、不得類推**：
        它們不回傳內容也不起子行程，containment 本身就是由 resolve() 組成的。"""
        import ast
        path = PACK / "scripts/validate.py"
        src = path.read_text(encoding="utf-8"); lines = src.split("\n")   # 不用 splitlines：檔內有 \v／U+2028 字面
        sys.path.insert(0, str(HERE)); import validate as V
        tree = ast.parse(src)
        tag = re.compile(r"READ-SITE (\d+)/(\d+)")
        hits, untagged, tagged = [], [], []
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            f = node.func
            name = f.attr if isinstance(f, ast.Attribute) else (f.id if isinstance(f, ast.Name) else None)
            base = None
            if isinstance(f, ast.Attribute):
                b = f.value
                while isinstance(b, ast.Attribute):
                    b = b.value
                base = b.id if isinstance(b, ast.Name) else None
            flagged = (name in V.READ_CALLS) or (base in V.READ_MODULES and name not in V.READ_MODULE_PURE)
            if not flagged:
                continue
            ln = node.lineno
            m = tag.search(lines[ln - 1]) or (tag.search(lines[ln - 2]) if ln >= 2 else None)
            hits.append((ln, name))
            if m:
                tagged.append((int(m.group(1)), int(m.group(2))))
            else:
                untagged.append((ln, name, lines[ln - 1].strip()[:60]))
        self.assertEqual(untagged, [], f"沒有 READ-SITE 標記的讀檔／執行站點：{untagged}")
        totals = {t for _, t in tagged}
        self.assertEqual(len(totals), 1, f"總數 N 不一致：{totals}")
        n = totals.pop()
        self.assertEqual(sorted(k for k, _ in tagged), list(range(1, n + 1)), tagged)
        self.assertEqual(len(V.READ_SITES), n, "封閉列舉表的列數必須等於標記總數")
        self.assertGreaterEqual(len(hits), 19, "AST 至少要看到 R15 點名的反向 glob 那一處")

    def test_read_site_detector_catches_unlisted_call_shapes(self):
        """R15 的 lens 各自注入的七種形狀，逐一確認新偵測器會紅（在本測試自己的 AST 走訪上驗，不改 tracked 檔）。"""
        import ast
        sys.path.insert(0, str(HERE)); import validate as V
        def any_flagged(snippet):
            for node in ast.walk(ast.parse(snippet)):
                if not isinstance(node, ast.Call):
                    continue
                f = node.func
                name = f.attr if isinstance(f, ast.Attribute) else (f.id if isinstance(f, ast.Name) else None)
                b = f.value if isinstance(f, ast.Attribute) else None
                while isinstance(b, ast.Attribute):
                    b = b.value
                base = b.id if isinstance(b, ast.Name) else None
                if (name in V.READ_CALLS) or (base in V.READ_MODULES and name not in V.READ_MODULE_PURE):
                    return True
            return False
        for snippet in ("open(p).read()", "p.glob('*')", "subprocess.Popen(['x'])", "os.listdir(p)",
                        "subprocess.check_output(['x'])", "shutil.copy(a, b)", "os.scandir(p)", "p.rglob('*')",
                        "os.walk(p)", "os.popen('x')", "json.load(fh)", "p.read_bytes()", "os.system('x')"):
            self.assertTrue(any_flagged(snippet), f"{snippet} 沒被偵測器認出")
        for snippet in ("p.is_file()", "p.resolve()", "p.exists()", "os.environ.get('X')", "p.relative_to(r)",
                        "os.path.normpath(x)", "os.path.isabs(x)"):
            self.assertFalse(any_flagged(snippet), f"{snippet} 是 metadata／環境／純字串運算，明示不在列舉內")

    def test_ci_neutraliser_is_the_same_implementation_as_the_output_boundary(self):
        """R14 logic L-4 / security S2：CI 的 sed 中和器是第二份實作——`[[:space:]]` 比 .NET
        IsWhiteSpace 小（U+00A0 穿過）、`^` 只認 `\n`（含 CR 的檔名穿過）。現在 CI 用
        scripts/neutralise.py（呼叫 LineSanitiser 同一份 `_neutralise`、同一個行界定義）。"""
        payload = ("File \"evil\r::error file=innocent.py,line=1,title=CI PASSED::x.py\", line 1\n"
                   "     ::stop-commands::PAYLOAD\n"
                   "  ##[error]V1\n"
                   " ::warning::u2028\n").encode("utf-8")
        r = subprocess.run([sys.executable, str(PACK / "scripts/neutralise.py")],
                           input=payload, capture_output=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        out = r.stdout.decode("utf-8")
        for line in out.replace("\r", "\n").splitlines():
            self.assertFalse(line.lstrip().startswith("::"), f"V2 穿過：{line!r}")
            self.assertNotIn("##[", line)
        self.assertIn("∷error file=innocent.py", out); self.assertIn("∷stop-commands", out)
        self.assertIn("##⟦error]V1", out)

    def test_ci_neutraliser_propagates_upstream_failure_and_keeps_bytes(self):
        """neutralise.py 只是過濾器：非 UTF-8 位元組不得讓它炸（errors=replace），且它本身
        exit 0——上游的非零由 `set -o pipefail` 保留（regression E-6 實測過 pipefail 生效）。"""
        r = subprocess.run([sys.executable, str(PACK / "scripts/neutralise.py")],
                           input=b"\xff\xfe::error::x\n", capture_output=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertNotIn(b"\n::error", b"\n" + r.stdout)

    # ---- #33 verify R15 ----

    def test_check_csvs_not_running_on_empty_lens_list_is_named(self):
        """R15 logic L-4：gate 相依只修了 `files is None`；`files == []`（lenses/ 沒有任何合法 CSV）時
        check_csvs 整支不跑（撞名、profile 名、catalog 與 lister 存在性四道檢查）且零訊息。"""
        lenses = self.fx.repo / "plugins/pai-lenses/lenses"
        for p in lenses.iterdir():
            p.unlink()
        (lenses / "BAD.CSV").write_text("key,focus\n", encoding="utf-8")
        out = self.assertRed()
        self.assertIn("check_csvs 沒有跑", out, out)

    def test_profile_list_in_annotation_is_neutralised_and_bounded(self):
        """R15 security S-2：lister 的 stderr 不進 annotation 了，但 **stdout**（PROFILES 的 key）仍原樣進
        「真源 PROFILES 有：…」——harness 是 PR 可控的 JS，key 可以是任意字串（含 `::`），也可以從
        repo 外檔案算出來。類級規則：任何子行程輸出進 annotation 都經 wc()（截斷 + 中和），這裡是第二處。"""
        h = self.fx.repo / "plugins/parallel-ai-agents/workflows/ensemble-workflow.js"
        src = h.read_text(encoding="utf-8")
        canary = "SECRET-FROM-OUTSIDE-" + "X" * 400
        src = src.replace("const PROFILES = {", "const PROFILES = {\n  '" + canary + "': { lenses: [] },", 1)
        h.write_text(src, encoding="utf-8")
        self.fx.write_lenses('key,focus\nx,"y"\n', profile="no-such-profile")
        out = self.assertRed(contains="真源 PROFILES 有")
        line = next(l for l in out.splitlines() if "真源 PROFILES 有" in l)
        self.assertIn("…（截斷）", line, "子行程 stdout 進 annotation 必須經 wc() 截斷")
        self.assertNotIn(canary, line, "整段內容不得原樣進 annotation")

    def test_mutation_check_restores_validate_on_sigterm(self):
        """R15 requirements F9：mutation 一輪被 SIGTERM 砍掉時（不是 Ctrl-C），被 mutate 的 validate.py
        無聲留在工作樹。handler 把 SIGTERM／SIGHUP 轉成 SystemExit，讓既有的 BaseException 還原路徑跑到。"""
        import signal
        sys.path.insert(0, str(HERE)); import mutation_check as M
        M.install_restore_signals()
        for sig in (signal.SIGTERM, signal.SIGHUP):
            h = signal.getsignal(sig)
            self.assertTrue(callable(h) and h is M._on_term, f"{sig} 沒有掛上還原 handler")
        with self.assertRaises(SystemExit):
            M._on_term(signal.SIGTERM, None)

    def test_no_repo_report_names_every_gate_in_the_closed_list(self):
        """R15 DA-3：`NO_REPO_GATES` 是本 commit 新造的手寫封閉列舉，零測試零靶。訊息必須逐一點名清單裡的每道閘門，
        且數量由清單算出——刪掉一條就紅。"""
        sys.path.insert(0, str(HERE)); import validate as V
        self._unlink_root_marketplace()
        out = self.assertRed(ci=True)
        for g in V.NO_REPO_GATES:
            self.assertIn(g, out, f"缺 repo 的回報必須點名 {g}")
        self.assertIn(f"{len(V.NO_REPO_GATES)} 道閘門", out)
        self.assertGreaterEqual(len(V.NO_REPO_GATES), 5)

    def test_no_repo_local_run_does_not_print_affirmative_tick_for_unverified_profile(self):
        """R15 DA-4：report_no_repo() 拿掉了否定式假訊息，卻留下肯定式的——獨立 pack 下不存在的 profile 仍印
        「N 條 lens ✓（profile 'x'）」。profile 名沒驗就不能打勾。"""
        self._unlink_root_marketplace()
        self.fx.write_lenses('key,focus\nx,"y"\n', profile="no-such-profile")
        out = self.assertGreen()
        self.assertNotIn("✓（profile 'no-such-profile'）", out, out)
        self.assertIn("名未驗——profile 名稱閘門沒有跑", out)

    def test_external_strings_entering_annotations_go_through_wc(self):
        """R15 DA-5：`mb.stderr` 沒走 wc() 而相鄰的 `changed.stderr` 走了。同類且**可觸發**的站點是 `--base` 字串
        本身（「base ref 'X' 不在本地歷史內」原樣回印）——merge-base 失敗時 git 不印 stderr，那一處的 wc() 是防禦、
        測不到；這裡釘住同一條規則：任何外部字串進 annotation 一律經 wc()。"""
        base = "nope-" + "z" * 400
        rc, out = self.fx.run("--base", base, "--event", "pull_request")
        self.assertEqual(rc, 1, out)
        self.assertNotIn("z" * 300, out, "外部字串原樣進了 annotation")
        self.assertIn("…（截斷）", out)

if __name__ == "__main__":
    unittest.main(verbosity=2)
