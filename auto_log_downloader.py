"""Download CoreGeek battle logs using the website's visible controls."""
import argparse
import hashlib
import json
import re
import sys
import subprocess
import tempfile
import time
from pathlib import Path

URL = "https://coregeek.rnd.huawei.com/GeneralIntro/1"
PHASES = ["练习赛", "海选", "64进32", "32进16", "16进8", "8进4", "决赛"]
FIELDS = ["队伍A", "A积分", "A分数", "队伍B", "B积分", "B分数", "地图", "完成时间", "状态"]
RESULTS = {"3": "win", "0": "lose", "1": "draw"}
DEFAULT_OUTPUT = Path("log")
REPO_ROOT = Path(__file__).resolve().parent
DECRYPT_TOOL = REPO_ROOT / "SecureLog" / "log_tool.py"
PRIVATE_KEY = REPO_ROOT / "AgentRace_LogKeys" / "private.pem"


def numbered_dirs(root, prefix):
    if not root.exists():
        return {}
    return {int(m[1]): p for p in root.iterdir() if p.is_dir()
            and (m := re.fullmatch(re.escape(prefix) + r'([0-9]+)', p.name))}


def prepare_round(root, resume=None, dry_run=False):
    rounds = numbered_dirs(root, 'round')
    number = resume if resume is not None else max(rounds, default=0) + 1
    target = rounds.get(number, root / ('round' + str(number)))
    if resume is not None and number not in rounds:
        raise ValueError('--round 只能指定已存在的轮次，用于补下载')
    previous = max((n for n in rounds if n < number), default=None)
    previous_games = numbered_dirs(rounds[previous], 'game') if previous is not None else {}
    games = numbered_dirs(target, 'game')
    next_game = max([*previous_games, *games], default=0) + 1
    known = {}
    for directory in games.values():
        info = directory / 'match.json'
        if info.exists():
            saved = json.loads(info.read_text(encoding='utf-8'))
            known[record_folder(saved['record'], saved['phase'])] = directory
    if not dry_run:
        if resume is None:
            root.mkdir(parents=True, exist_ok=True)
            target.mkdir()  # Never silently reuse a concurrently created round.
    return target, next_game, known


def parse_pages(value):
    if value.strip().lower() == "all":
        return None
    selected = set()
    for part in value.split(","):
        match = re.fullmatch(r"\s*([1-9]\d*)(?:-([1-9]\d*))?\s*", part)
        if not match:
            raise argparse.ArgumentTypeError("页码格式：1、3、2-5、1,3-5 或 all")
        first = int(match[1])
        last = int(match[2] or first)
        if last < first or last > 100000:
            raise argparse.ArgumentTypeError("页码范围无效（最大 100000）")
        selected.update(range(first, last + 1))
    return sorted(selected)


def safe_name(value):
    return re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", str(value)).strip(" .")[:80] or "unknown"


def parse_record(headers, values, team="OpenAI"):
    if len(headers) != len(values) or len(set(headers)) != len(headers):
        raise ValueError("表头与数据列数不一致，或存在重复表头")
    data = dict(zip(headers, values))
    if not all(key in data for key in FIELDS):
        raise ValueError("页面缺少所需表头")
    if team not in (data["队伍A"], data["队伍B"]):
        return None
    if data["状态"].strip().lower() in {"failure", "stopped"}:
        return None
    logs = []
    for letter, side in (("A", "BlueSide"), ("B", "RedSide")):
        score = data[letter + "分数"].strip()
        points = data[letter + "积分"].strip()
        if points not in RESULTS or not re.fullmatch(r"-?\d+(?:\.\d+)?", score):
            raise ValueError("分数或积分尚未就绪/无法识别")
        role = "ally" if data["队伍" + letter] == team else "enemy"
        logs.append({"label": "队伍" + letter + "日志", "team": data["队伍" + letter],
                     "filename": "{}_{}_{}_{}.log".format(role, side, score, RESULTS[points]),
                     "side": side, "score": score, "points": points, "result": RESULTS[points]})
    return {"record": {key: data[key] for key in FIELDS}, "logs": logs}


def record_folder(record, phase):
    raw = json.dumps([phase, record], ensure_ascii=False, sort_keys=True).encode("utf-8")
    digest = hashlib.sha256(raw).hexdigest()[:16]
    return safe_name(record["完成时间"]) + "_" + digest


def write_json(path, value):
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)


def checksum(path):
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def verified_existing(path, saved):
    return bool(saved and path.is_file() and path.stat().st_size > 0
                and path.stat().st_size == saved.get("bytes")
                and checksum(path) == saved.get("sha256"))


def decrypt_download(destination, saved):
    """Keep the raw download; publish restored text and report beside it."""
    with destination.open("rb") as stream:
        encrypted = any(b"ASL1 " in line or b"SECURE_LOG_DROPPED" in line
                        for line in stream)
    if not encrypted:
        return {"status": "plaintext"}
    output = destination.with_name(destination.stem + "_decrypted.log")
    report_path = Path(str(output) + ".report.json")
    previous = saved.get("decryption", {})
    if (previous.get("input_sha256") == saved["sha256"]
            and previous.get("status") in ("ok", "partial")
            and verified_existing(output, previous.get("output"))
            and verified_existing(report_path, previous.get("report"))):
        return previous
    # The tool refuses existing outputs. Stage both files before replacing them.
    with tempfile.TemporaryDirectory(prefix=".decrypt-", dir=destination.parent) as temp:
        staged = Path(temp) / output.name
        result = subprocess.run(
            [sys.executable, str(DECRYPT_TOOL), "decrypt", "--private", str(PRIVATE_KEY),
             "--input", str(destination.resolve()), "--out", str(staged.resolve()),
             "--backend", "rsa"], capture_output=True, text=True,
            encoding="utf-8", errors="replace")
        if result.returncode not in (0, 2):
            raise RuntimeError("解密失败（退出码 {}）：{}".format(
                result.returncode, (result.stderr or result.stdout).strip()))
        staged_report = Path(str(staged) + ".report.json")
        report = json.loads(staged_report.read_text(encoding="utf-8"))
        staged.replace(output)
        staged_report.replace(report_path)
    status = "ok" if result.returncode == 0 else "partial"
    print("[decrypt_download] {}：{}，恢复 {} 条记录".format(
        output.name, status, report.get("decoded_records", 0)), flush=True)
    return {"status": status, "input_sha256": saved["sha256"],
            "output": {"filename": output.name, "bytes": output.stat().st_size,
                       "sha256": checksum(output)},
            "report": {"filename": report_path.name, "bytes": report_path.stat().st_size,
                       "sha256": checksum(report_path)}}


def enter_records(page, phase, login_timeout):
    page.goto(URL, wait_until="domcontentloaded", timeout=60000)
    deadline = time.monotonic() + login_timeout
    clicked_login = False
    print("等待登录；若未自动登录，请在打开的浏览器中完成登录。", flush=True)
    while time.monotonic() < deadline:
        try:
            record_tab = page.get_by_role("tab", name="对战记录", exact=True)
            if record_tab.is_visible():
                record_tab.click()
                panel = page.get_by_role("tabpanel", name="对战记录", exact=True)
                panel.get_by_role("tab", name=phase, exact=True).click()
                panel.get_by_role("columnheader", name="A分数", exact=True).wait_for(timeout=30000)
                return panel
            # SSO may return to the homepage. Open the observed event route again.
            if page.url.rstrip("/") == "https://coregeek.rnd.huawei.com":
                page.goto(URL, wait_until="domcontentloaded", timeout=60000)
                continue
            login = page.get_by_text("登录", exact=True)
            if not clicked_login and login.count() == 1 and login.is_visible():
                login.click()
                clicked_login = True
        except Exception as exc:
            if page.is_closed():
                raise RuntimeError("浏览器已关闭") from exc
        page.wait_for_timeout(1000)
    raise RuntimeError("等待登录或对战记录页面超时，请确认内网连接和登录状态")


def snapshot(panel):
    headers = [s.strip() for s in panel.get_by_role("columnheader").all_text_contents()]
    if not all(key in headers for key in FIELDS):
        raise RuntimeError("表头与已适配页面不符，停止以免错误命名")
    rows = panel.get_by_role("row").filter(has=panel.page.get_by_role("combobox"))
    rows.first.wait_for(state='visible', timeout=30000)
    data = []
    for i in range(rows.count()):
        values = [s.strip() for s in rows.nth(i).get_by_role("cell").all_text_contents()]
        data.append(values)
    # The last cell changes when a menu option is selected; exclude it from pagination checks.
    signature = json.dumps([values[:9] for values in data], ensure_ascii=False)
    return headers, rows, data, signature


def save_download(page, row, label, destination, retries):
    last_error = None
    for attempt in range(retries):
        partial = destination.with_suffix(".log.part")
        try:
            page.keyboard.press("Escape")
            combo = row.get_by_role("combobox")
            if combo.get_attribute("aria-expanded") == "true":
                combo.click()
            combo.click()
            menu = page.get_by_role("menuitem", name=label, exact=True)
            with page.expect_download(timeout=60000) as pending:
                menu.click()
            download = pending.value
            download.save_as(str(partial))
            if partial.stat().st_size == 0:
                raise RuntimeError("下载文件为空")
            with partial.open("rb") as stream:
                prefix = stream.read(512).lstrip().lower()
            if prefix.startswith((b"<!doctype html", b"<html")):
                raise RuntimeError("下载返回了 HTML 页面")
            partial.replace(destination)
            return {"bytes": destination.stat().st_size, "sha256": checksum(destination),
                    "original_filename": download.suggested_filename}
        except Exception as exc:
            last_error = exc
            print("  下载尝试失败：" + str(exc), flush=True)
            if partial.exists():
                partial.unlink()
            if page.is_closed():
                break
            if attempt + 1 < retries:
                page.wait_for_timeout(1000 * (attempt + 1))
    raise RuntimeError("日志下载失败：" + type(last_error).__name__) from last_error


def run(page, args):
    panel = enter_records(page, args.phase, args.login_timeout)
    output, next_game, known_games = prepare_round(args.output.resolve(), args.round, args.dry_run)
    print('本轮目录：' + str(output), flush=True)
    summary = {"phase": args.phase, "team": args.team, "dry_run": args.dry_run,
               "downloaded": 0, "existing": 0, "matched": 0, "errors": [], "pages": 0,
               "completed": False, "unavailable": []}
    selected = args.pages
    summary["requested_pages"] = selected if selected is not None else "all"
    summary["processed_pages"] = []
    seen_pages = set()
    seen_records = set()
    try:
        while True:
            headers, rows, data, signature = snapshot(panel)
            if signature in seen_pages:
                raise RuntimeError("发现重复页面，停止避免翻页死循环")
            seen_pages.add(signature)
            summary["pages"] += 1
            current = summary["pages"]
            wanted = selected is None or current in selected
            print("{}第 {} 页，共 {} 条".format("处理" if wanted else "跳过", current, len(data)), flush=True)
            if wanted:
                summary["processed_pages"].append(current)
            for i, values in enumerate(data if wanted else []):
                try:
                    entry = parse_record(headers, values, args.team)
                    if entry is None:
                        continue
                    folder = record_folder(entry["record"], args.phase)
                    if folder in seen_records:
                        continue
                    seen_records.add(folder)
                    summary["matched"] += 1
                    if rows.nth(i).locator('.ant-select-disabled').count():
                        summary['unavailable'].append({'match': folder, 'reason': '网站禁用日志下载'})
                        print('  网站未提供此场日志，继续下一场。', flush=True)
                        continue
                    target = known_games.get(folder)
                    if target is None:
                        target = output / ('game' + str(next_game))
                        next_game += 1
                        known_games[folder] = target
                    if args.dry_run:
                        print(target.name + " / " + ", ".join(log["filename"] for log in entry["logs"]))
                        continue
                    target.mkdir(parents=True, exist_ok=True)
                    info_path = target / "match.json"
                    saved = {}
                    if info_path.exists():
                        saved = json.loads(info_path.read_text(encoding="utf-8")).get("downloads", {})
                    entry.update({"phase": args.phase, "downloads": saved})
                    write_json(info_path, entry)
                    for log in entry["logs"]:
                        name = log["filename"]
                        destination = target / name
                        try:
                            if verified_existing(destination, saved.get(name)):
                                summary["existing"] += 1
                            else:
                                saved[name] = save_download(page, rows.nth(i), log["label"], destination, args.retries)
                                summary["downloaded"] += 1
                                write_json(info_path, entry)
                                print("  已保存 " + target.name + "/" + name, flush=True)
                            saved[name]["decryption"] = decrypt_download(destination, saved[name])
                            write_json(info_path, entry)
                            if saved[name]["decryption"]["status"] == "partial":
                                raise RuntimeError("日志仅部分解密或无可解密记录，详见同级解密报告")
                        except Exception as exc:
                            summary["errors"].append({"match": folder, "file": name, "error": str(exc)})
                except Exception as exc:
                    summary["errors"].append({"page": summary["pages"], "row": i + 1,
                                              "record": values[:9], "error": str(exc)})
            if selected is not None and current >= max(selected):
                summary["completed"] = not summary["errors"]
                break
            next_page = panel.get_by_title("下一页", exact=True)
            if next_page.count() != 1:
                raise RuntimeError("未能唯一识别下一页按钮")
            if (next_page.get_attribute("aria-disabled") == "true"
                    or "ant-pagination-disabled" in (next_page.get_attribute("class") or "")):
                missing = [] if selected is None else [n for n in selected if n > current]
                if missing:
                    summary["errors"].append({"error": "请求的页码超出总页数", "missing_pages": missing})
                summary["completed"] = not summary["errors"]
                break
            next_page.click()
            deadline = time.monotonic() + 30
            while time.monotonic() < deadline:
                _, _, new_data, new_signature = snapshot(panel)
                if new_data and new_signature != signature:
                    break
                page.wait_for_timeout(300)
            else:
                raise RuntimeError("翻页后记录未更新")
    finally:
        if not args.dry_run:
            write_json(output / "summary.json", summary)
        print("本次下载 {} 个，跳过已验证文件 {} 个，错误 {} 个。".format(
            summary["downloaded"], summary["existing"], len(summary["errors"])), flush=True)
    return 2 if summary["errors"] else 0


def main():
    parser = argparse.ArgumentParser(description="自动下载 CoreGeek 双方对战日志，并按分数/积分命名")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT, help="round 目录的父文件夹（默认：当前工作目录下的 log/）")
    parser.add_argument("--round", type=int, help="补下载已存在的轮次；省略则创建下一轮")
    parser.add_argument("--profile", type=Path, default=Path(__file__).resolve().parent / ".browser-profile")
    parser.add_argument("--team", default="OpenAI")
    parser.add_argument("--phase", choices=PHASES, default="练习赛")
    parser.add_argument("--channel", choices=["msedge", "chrome", "chromium"], default="msedge")
    parser.add_argument("--ignore-https-errors", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--login-timeout", type=int, default=300)
    parser.add_argument("--retries", type=int, default=2)
    selection = parser.add_mutually_exclusive_group()
    selection.add_argument("--pages", type=parse_pages, default=[1], help="默认 1；例：3、2-5、1,3-5、all")
    selection.add_argument("--max-pages", type=int, help="兼容参数：前 N 页，0 表示全部")
    parser.add_argument("--dry-run", action="store_true", help="仅检查记录和打印文件名，不下载")
    args = parser.parse_args()
    if args.round is not None and args.round < 1:
        parser.error('--round 必须为正整数')
    if args.retries < 1 or args.login_timeout < 1 or (args.max_pages is not None and args.max_pages < 0):
        parser.error("重试/登录等待必须为正数，页数不能为负数")
    if args.max_pages is not None:
        args.pages = None if args.max_pages == 0 else list(range(1, args.max_pages + 1))
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("请先运行：python -m pip install playwright", file=sys.stderr)
        return 1
    with sync_playwright() as playwright:
        context = playwright.chromium.launch_persistent_context(
            str(args.profile.resolve()), channel=None if args.channel == "chromium" else args.channel,
            headless=False, accept_downloads=True, ignore_https_errors=True)
        context.set_default_timeout(15000)
        page = context.pages[0] if context.pages else context.new_page()
        try:
            return run(page, args)
        finally:
            context.close()


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("已停止，重新运行可补下载。", file=sys.stderr)
        sys.exit(130)
    except Exception as error:
        print("运行失败：" + str(error), file=sys.stderr)
        sys.exit(1)
