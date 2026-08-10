#!/usr/bin/env python3
"""`validate.py` 的回歸測試（stdlib unittest —— CI 沒有裝 pytest，也不該為此加依賴）。

**為什麼需要這個檔**（#33 verify R7）：`validate.py` 有十餘道閘門，出貨時零測試覆蓋 ——
所有錯誤分支只在 CI 的 happy path 被執行（也就是**都沒被執行**）。#33 的六輪 verify 有
超過二十個 finding 落在這一支，其中反覆出現的形狀是「閘門在某個條件下安靜蒸發並印肯定式
綠燈」。那類缺陷用讀的抓不到，只有實際餵一份壞掉的 fixture 才會現形。

所以這裡的每一條測試都對應**一個已經真實發生過的缺陷**，而不是為了覆蓋率。
每條測試都斷言**兩個方向**：壞的輸入要紅，好的輸入要綠 —— 只斷言其一的測試，
在閘門被整段拿掉時仍會通過。

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

    def run(self, *args):
        """回傳 (rc, 合併後的輸出)。validate.py 把 error 印到 stdout（GitHub annotation）。"""
        r = subprocess.run(
            [sys.executable, str(self.repo / "plugins/pai-lenses/scripts/validate.py"), *args],
            cwd=self.repo, capture_output=True, text=True,
            env={**os.environ, "GITHUB_ACTIONS": ""})
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

    def assertGreen(self, args=(), msg=""):
        rc, out = self.fx.run(*args)
        self.assertEqual(rc, 0, f"{msg}\n預期通過但 rc={rc}：\n{out}")
        return out

    def assertRed(self, args=(), contains=None, msg=""):
        rc, out = self.fx.run(*args)
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

    def test_missing_base_ref_is_error_not_silent_skip(self):
        self.assertRed(("--base", "0" * 40, "--event", "push"), contains="不在本地歷史內")

    def test_workflow_dispatch_without_base_is_not_an_error(self):
        """R5：一個結構上不可能綠的檢查，下一個人會直接把 fail-loud 拿掉。"""
        self.assertGreen(("--event", "workflow_dispatch"), msg="手動觸發")

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


if __name__ == "__main__":
    unittest.main(verbosity=2)
