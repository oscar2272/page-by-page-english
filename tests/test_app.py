import io
import base64
import json
import re
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image

from app import create_app, db_connect, display_page, hash_password, lesson_text
from scan import make_a4_preview
from worksheet_layout import normalize_page


def csrf_from(response):
    match = re.search(rb'name="_csrf" value="([^"]+)"', response.data)
    assert match, response.data[:500]
    return match.group(1).decode()


class StudyAppTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        with patch.dict("os.environ", {"INSTANCE_DIR": str(root / "instance")}):
            self.app = create_app({"TESTING": True, "DATABASE": str(root / "db.sqlite3"),
                                   "UPLOAD_DIR": str(root / "uploads")})
        self.client = self.app.test_client()
        with db_connect(root / "db.sqlite3") as db:
            db.execute("INSERT INTO users(username, display_name, password_hash, role) VALUES (?, ?, ?, ?)",
                       ("owner", "소유자", hash_password("owner-password-123"), "owner"))
            db.execute("INSERT INTO users(username, display_name, password_hash, role) VALUES (?, ?, ?, ?)",
                       ("reader", "독자", hash_password("reader-password-123"), "reader"))
            db.commit()
        self.db_path = root / "db.sqlite3"

    def tearDown(self):
        self.temp.cleanup()

    def login(self, username, password):
        token = csrf_from(self.client.get("/login"))
        return self.client.post("/login", data={"_csrf": token, "username": username,
                                                 "password": password}, follow_redirects=True)

    def make_material(self):
        self.login("owner", "owner-password-123")
        image = Image.new("RGB", (40, 30), "white")
        output = io.BytesIO()
        image.save(output, "JPEG")
        output.seek(0)
        token = csrf_from(self.client.get("/materials/new"))
        response = self.client.post("/materials/new", data={
            "_csrf": token, "title": "Verb practice", "study_date": "2026-10-07",
            "content": "## Verbs\nI walk to school.", "photos": (output, "page.jpg")},
            content_type="multipart/form-data", follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Verb practice", response.data)
        with db_connect(self.db_path) as db:
            return db.execute("SELECT id FROM materials").fetchone()["id"]

    def test_invited_reader_can_comment_but_cannot_edit(self):
        material_id = self.make_material()
        token = csrf_from(self.client.get(f"/materials/{material_id}"))
        self.client.post("/logout", data={"_csrf": token})
        self.assertEqual(self.client.get(f"/materials/{material_id}").status_code, 200)
        self.login("reader", "reader-password-123")
        page = self.client.get(f"/materials/{material_id}")
        self.assertEqual(page.status_code, 200)
        token = csrf_from(page)
        comment = self.client.post(f"/materials/{material_id}/comments",
                                   data={"_csrf": token, "body": "좋은 자료예요"}, follow_redirects=True)
        self.assertIn("좋은 자료예요".encode(), comment.data)
        self.assertEqual(self.client.get(f"/materials/{material_id}/edit").status_code, 403)
        self.assertEqual(self.client.post(f"/materials/{material_id}/questions/new",
                                          data={"_csrf": token, "prompt": "x", "answer": "y"}).status_code, 403)

    def test_direct_photo_links_are_public(self):
        self.make_material()
        with db_connect(self.db_path) as db:
            photo_id = db.execute("SELECT id FROM photos").fetchone()["id"]
        path = f"/photos/{photo_id}/preview"
        response = self.client.get(path)
        self.assertEqual(response.status_code, 200)
        response.close()
        token = csrf_from(self.client.get("/"))
        self.client.post("/logout", data={"_csrf": token})
        response = self.client.get(path)
        self.assertEqual(response.status_code, 200)
        response.close()
        self.login("reader", "reader-password-123")
        response = self.client.get(path)
        self.assertEqual(response.status_code, 200)
        response.close()
        with db_connect(self.db_path) as db:
            db.execute("UPDATE users SET active = 0 WHERE username = 'reader'")
            db.commit()
        response = self.client.get(path)
        self.assertEqual(response.status_code, 200)
        response.close()

    def test_a4_reading_page_keeps_original_and_prints_in_order(self):
        material_id = self.make_material()
        with db_connect(self.db_path) as db:
            photo = db.execute("SELECT id, packet_id, original_path, preview_path FROM photos").fetchone()
            photo_id, packet_id = photo["id"], photo["packet_id"]
            original_bytes = Path(photo["original_path"]).read_bytes()
        reading = self.client.get(f"/photos/{photo_id}/reading")
        self.assertEqual(reading.status_code, 200)
        self.assertEqual(Image.open(io.BytesIO(reading.data)).size, (1654, 2339))
        reading.close()
        self.assertEqual(Path(photo["original_path"]).read_bytes(), original_bytes)
        self.assertIn(f"/photos/{photo_id}/preview".encode(), self.client.get(f"/materials/{material_id}/read?packet_id={packet_id}").data)
        self.assertIn(f"/photos/{photo_id}/preview".encode(), self.client.get(f"/materials/{material_id}/print").data)
        self.assertIn(b"data:image/jpeg;base64,", self.client.get(f"/materials/{material_id}/export.html").data)
        self.assertEqual(self.client.get(f"/materials/{material_id}/read?packet_id=9999").status_code, 404)

    def test_rendered_page_preserves_source_and_editable_handwriting_explanation(self):
        material_id = self.make_material()
        with db_connect(self.db_path) as db:
            photo_id = db.execute("SELECT id FROM photos WHERE material_id = ?", (material_id,)).fetchone()["id"]
        editor = self.client.get(f"/photos/{photo_id}/render/edit")
        self.assertEqual(editor.status_code, 200)
        saved = self.client.post(f"/photos/{photo_id}/render/edit", data={
            "_csrf": csrf_from(editor), "title": "Did", "block_key": ["0", "1"],
            "block_kind_0": "example", "block_text_0": "Did you go?",
            "block_explanation_0": "", "block_kind_1": "handwriting",
            "block_text_1": "<listen>", "block_explanation_1": "a listen을 명사로 사용한 표시",
            "block_uncertain_1": "1"}, follow_redirects=True)
        self.assertEqual(saved.status_code, 200)
        self.assertIn("필기 해설".encode(), saved.data)
        self.assertIn(b"&lt;listen&gt;", saved.data)
        self.assertIn("원본 확인 필요".encode(), saved.data)
        self.assertIn(f"/photos/{photo_id}/preview".encode(), saved.data)
        self.assertIn("a listen을 명사로 사용한 표시".encode(), self.client.get(f"/materials/{material_id}/print").data)
        self.assertIn("a listen을 명사로 사용한 표시".encode(), self.client.get(f"/materials/{material_id}/export.html").data)
        with db_connect(self.db_path) as db:
            self.assertIn("handwriting", db.execute("SELECT rendered_json FROM photos WHERE id = ?", (photo_id,)).fetchone()[0])
        ai_attempt = self.client.post(f"/photos/{photo_id}/render/ai", data={"_csrf": csrf_from(saved)})
        self.assertEqual(ai_attempt.status_code, 302)

    def test_versioned_layout_keeps_callout_and_table_without_word_rules(self):
        material_id = self.make_material()
        with db_connect(self.db_path) as db:
            photo = db.execute("SELECT id, packet_id FROM photos WHERE material_id = ?", (material_id,)).fetchone()
            photo_id, packet_id = photo["id"], photo["packet_id"]
            page = normalize_page({"title": "Worksheet", "blocks": [
                {"kind": "text", "text": "A = B", "explanation": "", "uncertain": False,
                 "region": "callout", "group": 0, "background": "#e6e6e6", "border": False,
                 "text_style": "bold", "cells": [], "spans": [
                     {"text": "A = ", "text_style": "normal"}, {"text": "B", "text_style": "bold"}]},
                {"kind": "text", "text": "Description", "explanation": "", "uncertain": False,
                 "region": "callout", "group": 0, "background": "#e6e6e6", "border": False,
                 "text_style": "normal", "cells": []},
                {"kind": "heading", "text": "", "explanation": "", "uncertain": False,
                 "region": "table", "group": 1, "background": "", "border": True,
                 "text_style": "bold", "cells": ["First", "Second"]},
                {"kind": "text", "text": "", "explanation": "", "uncertain": False,
                 "region": "table", "group": 1, "background": "", "border": True,
                 "text_style": "normal", "cells": ["One", "Two"]},
            ]})
            db.execute("UPDATE photos SET rendered_json = ? WHERE id = ?", (json.dumps(page), photo_id))
            db.execute("INSERT INTO render_jobs(packet_id, status, total, completed) VALUES (?, 'succeeded', 1, 1)", (packet_id,))
            db.commit()
        episode = self.client.get(f"/materials/{material_id}/read?packet_id={packet_id}")
        self.assertEqual(episode.status_code, 200)
        self.assertIn(b"worksheet-callout", episode.data)
        self.assertIn(b"worksheet-table", episode.data)
        self.assertIn(b"worksheet-inline-normal", episode.data)
        self.assertIn(b"worksheet-inline-bold", episode.data)
        self.assertIn(b"background-color:#e6e6e6", episode.data)
        printed = self.client.get(f"/materials/{material_id}/print")
        self.assertIn(b"worksheet-callout", printed.data)
        self.assertIn(b"worksheet-table", printed.data)
        editor = self.client.get(f"/photos/{photo_id}/render/edit")
        self.assertEqual(editor.status_code, 200)
        self.assertIn(b"block_group_0", editor.data)
        self.assertIn(b"block_spans_0", editor.data)
        self.assertEqual(display_page(page)["regions"][0]["blocks"][1]["index"], 1)
        broken = {**page, "blocks": [dict(block) for block in page["blocks"]]}
        broken["blocks"][-1]["region"] = "invalid"
        with self.assertRaises(ValueError):
            normalize_page(broken)
        empty_scaffold = {**page["blocks"][0], "text": "", "spans": [], "background": "", "border": False}
        cleaned = normalize_page({"title": "Worksheet", "blocks": [empty_scaffold, *page["blocks"]]})
        self.assertEqual(len(cleaned["blocks"]), len(page["blocks"]))
        blank_table_row = {**page["blocks"][2], "text": "", "cells": ["", ""]}
        table_with_blank_row = normalize_page({"title": "Worksheet", "blocks": [*page["blocks"], blank_table_row]})
        self.assertEqual(table_with_blank_row["blocks"][-1]["cells"], ["", ""])
        with self.assertRaisesRegex(ValueError, "옮길 내용을 찾지 못했습니다"):
            normalize_page({"title": "Worksheet", "blocks": [empty_scaffold]})
        invalid_spans = {**page["blocks"][0], "spans": [{"text": "wrong", "text_style": "bold"}]}
        fallback = normalize_page({"title": "Worksheet", "blocks": [invalid_spans]})
        self.assertEqual(fallback["blocks"][0]["text"], "A = B")
        self.assertEqual(fallback["blocks"][0]["spans"], [])

    def test_one_page_ai_result_is_saved_with_usage_and_no_other_pages_changed(self):
        material_id = self.make_material()
        with db_connect(self.db_path) as db:
            photo_id = db.execute("SELECT id FROM photos WHERE material_id = ?", (material_id,)).fetchone()["id"]
            db.execute("UPDATE settings SET value = '1' WHERE key = 'api_ai_enabled'")
            db.commit()
        result = ({"title": "Did", "blocks": [{"kind": "handwriting", "text": "listen",
                   "explanation": "동사와 다른 표현", "uncertain": False,
                   "region": "body", "group": 0, "background": "", "border": False,
                   "text_style": "normal", "cells": []}]},
                  {"input_tokens": 700, "output_tokens": 500})
        audit = ({"passed": True, "issues": []}, {"input_tokens": 120, "output_tokens": 40})
        with patch("app.paid_ai_ready", return_value=True), patch("app.call_ai", side_effect=[result, audit]) as ai:
            token = csrf_from(self.client.get(f"/materials/{material_id}/read"))
            response = self.client.post(f"/photos/{photo_id}/render/ai", data={"_csrf": token}, follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn("동사와 다른 표현".encode(), response.data)
        self.assertEqual(ai.call_count, 2)
        self.assertEqual(ai.call_args_list[0].kwargs["model"], "gpt-4.1-mini")
        self.assertEqual(ai.call_args_list[0].kwargs["max_output_tokens"], 8000)
        with db_connect(self.db_path) as db:
            usage = db.execute("SELECT photo_id, model, input_tokens, output_tokens FROM ai_usage").fetchone()
            self.assertEqual(tuple(usage), (photo_id, "gpt-4.1-mini", 820, 540))

    def test_packet_conversion_rolls_back_all_pages_if_later_page_fails(self):
        material_id = self.make_material()
        with db_connect(self.db_path) as db:
            first = db.execute("SELECT * FROM photos WHERE material_id = ?", (material_id,)).fetchone()
            packet_id = first["packet_id"]
            db.execute("UPDATE photos SET rendered_json = ? WHERE id = ?", ('{"title":"old","blocks":[]}', first["id"]))
            db.execute("INSERT INTO photos(material_id, packet_id, original_name, original_path, preview_path, mime_type, position) VALUES (?, ?, ?, ?, ?, ?, ?)",
                       (material_id, packet_id, "second.jpg", first["original_path"], first["preview_path"], first["mime_type"], 2))
        class ImmediateThread:
            def __init__(self, target, args, daemon):
                self.target, self.args = target, args
            def start(self):
                self.target(*self.args)
        result = ({"title": "new", "blocks": [{"kind": "text", "text": "new", "explanation": "", "uncertain": False}]},
                  {"input_tokens": 10, "output_tokens": 10}, "gpt-6.1-sol")
        with patch("app.ai_ready", return_value=True), patch("app.threading.Thread", ImmediateThread), \
             patch("app.render_photo_with_ai", side_effect=[result, RuntimeError("Plus 사용량 한도")]):
            token = csrf_from(self.client.get(f"/materials/{material_id}/read"))
            response = self.client.post(f"/materials/{material_id}/packets/{packet_id}/render/ai",
                data={"_csrf": token, "replace": "1"}, follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn("Plus 사용량 한도".encode(), response.data)
        with db_connect(self.db_path) as db:
            pages = db.execute("SELECT rendered_json FROM photos WHERE packet_id = ? ORDER BY position", (packet_id,)).fetchall()
            self.assertEqual([row[0] for row in pages], ['{"title":"old","blocks":[]}', ""])
            self.assertEqual(db.execute("SELECT COUNT(*) FROM ai_usage").fetchone()[0], 0)
            self.assertEqual(db.execute("SELECT status FROM render_jobs").fetchone()[0], "failed")

    def test_visual_audit_rejects_unresolved_layout_without_overwriting(self):
        material_id = self.make_material()
        with db_connect(self.db_path) as db:
            photo_id = db.execute("SELECT id FROM photos WHERE material_id = ?", (material_id,)).fetchone()[0]
            db.execute("UPDATE photos SET rendered_json = ? WHERE id = ?", ('{"title":"old","blocks":[]}', photo_id))
            db.execute("UPDATE settings SET value = '1' WHERE key = 'api_ai_enabled'")
        candidate = ({"title": "Page", "blocks": [{"kind": "text", "text": "A", "explanation": "", "uncertain": False,
            "region": "body", "group": 0, "background": "", "border": False, "text_style": "normal", "cells": []}]},
            {"input_tokens": 10, "output_tokens": 10})
        rejected = ({"passed": False, "issues": ["회색 상자 누락"]}, {"input_tokens": 10, "output_tokens": 10})
        with patch("app.paid_ai_ready", return_value=True), patch("app.call_ai", side_effect=[candidate, rejected, candidate, rejected]):
            token = csrf_from(self.client.get(f"/photos/{photo_id}/render/edit"))
            response = self.client.post(f"/photos/{photo_id}/render/ai", data={"_csrf": token, "replace": "1"}, follow_redirects=True)
        self.assertIn("회색 상자 누락".encode(), response.data)
        with db_connect(self.db_path) as db:
            self.assertEqual(db.execute("SELECT rendered_json FROM photos WHERE id = ?", (photo_id,)).fetchone()[0], '{"title":"old","blocks":[]}')
            self.assertEqual(db.execute("SELECT COUNT(*) FROM ai_usage").fetchone()[0], 0)

    def test_packet_conversion_retries_incomplete_stream_before_commit(self):
        material_id = self.make_material()
        with db_connect(self.db_path) as db:
            packet_id = db.execute("SELECT packet_id FROM photos WHERE material_id = ?", (material_id,)).fetchone()[0]
        class ImmediateThread:
            def __init__(self, target, args, daemon):
                self.target, self.args = target, args
            def start(self):
                self.target(*self.args)
        result = ({"title": "Did", "blocks": []}, {"input_tokens": 10, "output_tokens": 10}, "gpt-6.1-sol")
        with patch("app.ai_ready", return_value=True), patch("app.threading.Thread", ImmediateThread), \
             patch("app.time.sleep"), patch("app.render_photo_with_ai", side_effect=[
                 RuntimeError("ChatGPT 응답이 끝까지 도착하지 않았습니다."), result]) as render:
            token = csrf_from(self.client.get(f"/materials/{material_id}/read"))
            response = self.client.post(f"/materials/{material_id}/packets/{packet_id}/render/ai",
                data={"_csrf": token}, follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(render.call_count, 2)
        with db_connect(self.db_path) as db:
            self.assertEqual(db.execute("SELECT status FROM render_jobs").fetchone()[0], "succeeded")
            self.assertEqual(db.execute("SELECT COUNT(*) FROM ai_usage").fetchone()[0], 1)

    def converted_episode(self, material_id):
        with db_connect(self.db_path) as db:
            photo = db.execute("SELECT id, packet_id FROM photos WHERE material_id = ?", (material_id,)).fetchone()
            db.execute("UPDATE photos SET rendered_json = ? WHERE id = ?",
                       ('{"title":"Did","blocks":[{"kind":"text","text":"Did you go?","explanation":"","uncertain":false}]}', photo["id"]))
            db.execute("INSERT INTO render_jobs(packet_id, status, completed, total) VALUES (?, 'succeeded', 1, 1)", (photo["packet_id"],))
            return photo["id"], photo["packet_id"]

    def test_original_shading_and_table_structure_are_recreated(self):
        page = display_page({"title": "Sheet", "blocks": [
            {"kind": "text", "text": "💡 Make = you build it.\n\n(Think of MAKE as building.)", "explanation": "", "uncertain": False},
            {"kind": "heading", "text": "🇰🇷 VERB-FIRST THINKING    🇺🇸 NATURAL ENGLISH CHUNK", "explanation": "", "uncertain": False},
            {"kind": "example", "text": "“Decide quickly.”    “Make a quick decision.”", "explanation": "", "uncertain": False},
        ]})
        self.assertEqual([block["appearance"] for block in page["blocks"]],
                         ["shaded", "table_header", "table_row"])
        self.assertEqual(page["blocks"][2]["cells"], ["“Decide quickly.”", "“Make a quick decision.”"])
        self.assertEqual(page["blocks"][0]["callout_body"], "(Think of MAKE as building.)")
        self.assertEqual(display_page({"title": "", "blocks": [{"kind": "text", "text": "💡 Plain",
            "appearance": "plain", "explanation": "", "uncertain": False}]})["blocks"][0]["appearance"], "plain")
        title_page = display_page({"title": "Two Line Title", "blocks": [{"kind": "heading",
            "text": "Two Line\nTitle", "explanation": "", "uncertain": False},
            {"kind": "text", "text": "A subtitle", "explanation": "", "uncertain": False}]})
        self.assertFalse(title_page["show_title"])
        self.assertEqual([block["appearance"] for block in title_page["blocks"]], ["document_title", "subtitle"])
        material_id = self.make_material()
        photo_id, packet_id = self.converted_episode(material_id)
        with db_connect(self.db_path) as db:
            db.execute("UPDATE photos SET rendered_json = ? WHERE id = ?", (json.dumps(page), photo_id))
        html = self.client.get(f"/materials/{material_id}/read?packet_id={packet_id}").data
        self.assertIn(b"episode-shaded", html)
        self.assertIn(b"episode-table-header", html)
        self.assertIn(b"episode-table-row", html)

    def test_episode_notes_require_full_ai_conversion_and_stay_private(self):
        material_id = self.make_material()
        with db_connect(self.db_path) as db:
            photo = db.execute("SELECT id, packet_id FROM photos WHERE material_id = ?", (material_id,)).fetchone()
            photo_id, packet_id = photo["id"], photo["packet_id"]
        before = self.client.get(f"/materials/{material_id}/read?packet_id={packet_id}")
        self.assertNotIn(b'id="place-note"', before.data)
        self.assertNotIn(b'episode-ink-layer', before.data)
        note_url = f"/materials/{material_id}/packets/{packet_id}/annotations"
        self.assertEqual(self.client.post(note_url, data={"_csrf": csrf_from(before), "photo_id": photo_id,
            "anchor_y": "4321", "body": "did 뒤 동사원형이 헷갈림"}).status_code, 400)
        self.converted_episode(material_id)
        page = self.client.get(f"/materials/{material_id}/read?packet_id={packet_id}")
        self.assertIn(b'id="place-note"', page.data)
        self.assertIn(b'id="episode-stream"', page.data)
        self.assertIn(b'episode-ink-layer', page.data)
        self.assertIn(b'id="ink-pen"', page.data)
        self.assertNotIn(b'class="story-page"', page.data)
        self.assertNotIn(b'class="episode-original"', page.data)
        self.assertEqual(self.client.get(f"/photos/{photo_id}/note").status_code, 404)
        saved = self.client.post(note_url, data={"_csrf": csrf_from(page), "photo_id": photo_id,
            "anchor_y": "4321", "anchor_block": "0", "block_y": "6500",
            "body": "did 뒤 동사원형이 헷갈림"})
        self.assertEqual(saved.status_code, 200)
        self.assertEqual((saved.json["anchor_block"], saved.json["block_y"]), (0, 6500))
        note_id = saved.json["id"]
        second = self.client.post(note_url, data={"_csrf": csrf_from(page), "photo_id": photo_id,
            "anchor_y": "8123", "body": "다른 위치의 메모"})
        self.assertEqual(second.status_code, 200)
        with db_connect(self.db_path) as db:
            lesson = db.execute("SELECT * FROM materials WHERE id = ?", (material_id,)).fetchone()
            self.assertIn("did 뒤 동사원형이 헷갈림", lesson_text(db, lesson))
            self.assertEqual(db.execute("SELECT COUNT(*) FROM episode_annotations").fetchone()[0], 2)
        with patch("app.ai_ready", return_value=True), patch("app.call_ai", return_value={"questions": [{
            "kind": "short", "prompt": "Did you go?", "answer": "Yes", "explanation": "test"}]}) as ai:
            self.client.post(f"/materials/{material_id}/questions/generate", data={"_csrf": csrf_from(page)})
            self.assertIn("did 뒤 동사원형이 헷갈림", ai.call_args.args[0][0]["text"])
        with patch("app.ai_ready", return_value=True), patch("app.call_ai", return_value={"report": "동사원형 복습 후보"}):
            insight = self.client.post(f"/materials/{material_id}/packets/{packet_id}/insight",
                data={"_csrf": csrf_from(page)}, follow_redirects=True)
            self.assertIn("동사원형 복습 후보".encode(), insight.data)
        self.client.post("/logout", data={"_csrf": csrf_from(self.client.get("/"))})
        self.assertNotIn("did 뒤 동사원형이 헷갈림".encode(), self.client.get(f"/materials/{material_id}/read?packet_id={packet_id}").data)
        self.login("reader", "reader-password-123")
        self.assertEqual(self.client.post(f"/annotations/{note_id}/delete", data={"_csrf": csrf_from(self.client.get("/"))}).status_code, 403)

    def test_episode_ink_is_private_and_used_after_review(self):
        material_id = self.make_material()
        photo_id, packet_id = self.converted_episode(material_id)
        page = self.client.get(f"/materials/{material_id}/read?packet_id={packet_id}")
        url = f"/materials/{material_id}/packets/{packet_id}/ink/{photo_id}"
        strokes = json.dumps([{"tool": "pen", "points": [[0.1, 0.2], [0.3, 0.4]]}])
        saved = self.client.post(url, data={"_csrf": csrf_from(page), "strokes": strokes, "recognized_text": "did + 동사원형"})
        self.assertEqual(saved.status_code, 200)
        with db_connect(self.db_path) as db:
            lesson = db.execute("SELECT * FROM materials WHERE id = ?", (material_id,)).fetchone()
            self.assertIn("did + 동사원형", lesson_text(db, lesson))
        changed = json.dumps([{"tool": "pen", "points": [[0.2, 0.2]]}])
        response = self.client.post(url, data={"_csrf": csrf_from(page), "strokes": changed, "recognized_text": "did + 동사원형"})
        self.assertEqual(response.json["recognized_text"], "")
        self.client.post("/logout", data={"_csrf": csrf_from(self.client.get("/"))})
        self.assertNotIn(b'episode-ink-data', self.client.get(f"/materials/{material_id}/read?packet_id={packet_id}").data)
        self.login("reader", "reader-password-123")
        self.assertEqual(self.client.post(url, data={"_csrf": csrf_from(self.client.get("/")), "strokes": strokes}).status_code, 403)

    def test_episode_pencil_note_can_be_recognized_on_explicit_request(self):
        material_id = self.make_material()
        photo_id, packet_id = self.converted_episode(material_id)
        image = io.BytesIO()
        Image.new("RGB", (1200, 720), "white").save(image, "PNG")
        data = "data:image/png;base64," + base64.b64encode(image.getvalue()).decode()
        page = self.client.get(f"/materials/{material_id}/read?packet_id={packet_id}")
        saved = self.client.post(f"/materials/{material_id}/packets/{packet_id}/annotations", data={
            "_csrf": csrf_from(page), "photo_id": photo_id, "anchor_y": "5000", "drawing_data": data})
        self.assertEqual(saved.status_code, 200)
        note_id = saved.json["id"]
        drawing = self.client.get(f"/annotations/{note_id}/drawing")
        self.assertEqual(drawing.status_code, 200)
        drawing.close()
        with patch("app.ai_ready", return_value=True), patch("app.call_ai", return_value=(
            {"text": "did + 동사원형", "uncertain": False}, {"input_tokens": 10, "output_tokens": 4})):
            recognized = self.client.post(f"/annotations/{note_id}/recognize", data={"_csrf": csrf_from(page)})
        self.assertEqual(recognized.json["recognized_text"], "did + 동사원형")
        with db_connect(self.db_path) as db:
            self.assertEqual(db.execute("SELECT recognized_text FROM episode_annotations WHERE id = ?", (note_id,)).fetchone()[0], "did + 동사원형")

    def test_stapled_packets_keep_pages_and_notes_separate(self):
        self.login("owner", "owner-password-123")
        def page(name):
            output = io.BytesIO()
            Image.new("RGB", (40, 30), "white").save(output, "JPEG")
            output.seek(0)
            return output, name
        token = csrf_from(self.client.get("/materials/new"))
        created = self.client.post("/materials/new", data={
            "_csrf": token, "title": "Grammar", "study_date": "2026-10-10",
            "packet_title": "did", "photos": [page("did-1.jpg"), page("did-2.jpg")]},
            content_type="multipart/form-data", follow_redirects=True)
        self.assertEqual(created.status_code, 200)
        with db_connect(self.db_path) as db:
            material_id = db.execute("SELECT id FROM materials").fetchone()["id"]
            did = db.execute("SELECT id FROM material_packets WHERE title = 'did'").fetchone()["id"]
        token = csrf_from(self.client.get(f"/materials/{material_id}"))
        added = self.client.post(f"/materials/{material_id}/packets", data={
            "_csrf": token, "title": "when", "content": "When did you go?",
            "photos": [page("when-1.jpg"), page("when-2.jpg"), page("when-3.jpg")]},
            content_type="multipart/form-data", follow_redirects=True)
        self.assertEqual(added.status_code, 200)
        with db_connect(self.db_path) as db:
            when = db.execute("SELECT id FROM material_packets WHERE title = 'when'").fetchone()["id"]
            counts = db.execute("SELECT packet_id, COUNT(*) AS n FROM photos GROUP BY packet_id ORDER BY packet_id").fetchall()
            self.assertEqual([(r["packet_id"], r["n"]) for r in counts], [(did, 2), (when, 3)])
            photo_id = db.execute("SELECT id FROM photos WHERE packet_id = ? ORDER BY id LIMIT 1", (did,)).fetchone()["id"]
        for path in (f"/materials/{material_id}", f"/materials/{material_id}/print", f"/materials/{material_id}/export.html"):
            body = self.client.get(path).data
            self.assertIn(b"did", body)
            self.assertIn(b"when", body)
            if path.endswith(("/print", "/export.html")):
                self.assertIn(b"When did you go?", body)
            self.assertLess(body.index(b"did-1.jpg"), body.index(b"when-1.jpg"))
        token = csrf_from(self.client.get(f"/materials/{material_id}"))
        self.client.post(f"/materials/{material_id}/photos/{photo_id}/packet", data={"_csrf": token, "packet_id": str(when)})
        with db_connect(self.db_path) as db:
            self.assertEqual(db.execute("SELECT packet_id FROM photos WHERE id = ?", (photo_id,)).fetchone()[0], when)

    def test_two_packets_can_be_created_in_one_lesson_submission(self):
        self.login("owner", "owner-password-123")
        form = self.client.get("/materials/new")
        self.assertIn(b'id="add-packet"', form.data)
        self.assertIn(b'material_form.js', form.data)
        def page(name):
            output = io.BytesIO()
            Image.new("RGB", (40, 30), "white").save(output, "JPEG")
            output.seek(0)
            return output, name
        response = self.client.post("/materials/new", data={
            "_csrf": csrf_from(form), "title": "One class, two packets", "study_date": "2026-10-10",
            "packet_key": ["0", "1"], "packet_title_0": "did", "packet_content_0": "Did you go?",
            "packet_photos_0": [page("did-1.jpg"), page("did-2.jpg")],
            "packet_title_1": "when", "packet_content_1": "When did you go?",
            "packet_photos_1": [page("when-1.jpg"), page("when-2.jpg"), page("when-3.jpg")]},
            content_type="multipart/form-data", follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        self.assertLess(response.data.index(b"did-1.jpg"), response.data.index(b"when-1.jpg"))
        with db_connect(self.db_path) as db:
            rows = db.execute("""SELECT material_packets.title, material_packets.content, COUNT(photos.id) AS pages
                FROM material_packets LEFT JOIN photos ON photos.packet_id = material_packets.id
                GROUP BY material_packets.id ORDER BY material_packets.position""").fetchall()
            self.assertEqual([(r["title"], r["content"], r["pages"]) for r in rows],
                             [("did", "Did you go?", 2), ("when", "When did you go?", 3)])
            material_id = db.execute("SELECT id FROM materials").fetchone()["id"]
            did_id = db.execute("SELECT id FROM material_packets WHERE title = 'did'").fetchone()["id"]
        page = self.client.get(f"/materials/{material_id}")
        self.assertIn("1회차 / 전체 2회차".encode(), page.data)
        self.assertNotIn(b'name="position"', page.data)
        token = csrf_from(page)
        self.client.post(f"/materials/{material_id}/packets/{did_id}/order",
                         data={"_csrf": token, "direction": "down"})
        with db_connect(self.db_path) as db:
            titles = [r["title"] for r in db.execute("SELECT title FROM material_packets ORDER BY position, id")]
        self.assertEqual(titles, ["when", "did"])

    def test_a4_scan_keeps_marks_on_image_edges(self):
        image = Image.new("RGB", (120, 160), "white")
        for y in range(20, 140):
            image.putpixel((119, y), (220, 0, 0))
        source = io.BytesIO()
        image.save(source, "JPEG", quality=95)
        result, mode = make_a4_preview(source.getvalue())
        self.assertEqual(mode, "estimated")
        scanned = Image.open(io.BytesIO(result))
        self.assertEqual(scanned.size, (1654, 2339))
        self.assertLess(scanned.getpixel((1650, 1000))[1], 180)

    def test_owner_can_reorder_delete_one_and_clear_a_nine_page_packet(self):
        self.login("owner", "owner-password-123")
        def page(number):
            output = io.BytesIO()
            Image.new("RGB", (40, 30), "white").save(output, "JPEG")
            output.seek(0)
            return output, f"page-{number}.jpg"
        token = csrf_from(self.client.get("/materials/new"))
        response = self.client.post("/materials/new", data={
            "_csrf": token, "title": "Nine pages", "study_date": "2026-10-10",
            "packet_key": "0", "packet_title_0": "did",
            "packet_photos_0": [page(number) for number in range(1, 10)]},
            content_type="multipart/form-data", follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"page-9.jpg", response.data)
        self.assertNotIn("이 묶음의 내용과 필기".encode(), self.client.get("/materials/new").data)
        with db_connect(self.db_path) as db:
            material_id = db.execute("SELECT id FROM materials").fetchone()["id"]
            packet_id = db.execute("SELECT id FROM material_packets").fetchone()["id"]
            photos = db.execute("SELECT * FROM photos ORDER BY position").fetchall()
            self.assertEqual(len(photos), 9)
            self.assertEqual([p["original_name"] for p in photos], [f"page-{n}.jpg" for n in range(1, 10)])
            ninth_id = photos[-1]["id"]
            second_id = photos[1]["id"]
            original_path = Path(photos[-1]["original_path"])
        token = csrf_from(self.client.get(f"/materials/{material_id}"))
        self.client.post(f"/materials/{material_id}/photos/{second_id}/order",
                         data={"_csrf": token, "direction": "up"})
        with db_connect(self.db_path) as db:
            first_two = db.execute("SELECT original_name FROM photos ORDER BY position LIMIT 2").fetchall()
            self.assertEqual([r["original_name"] for r in first_two], ["page-2.jpg", "page-1.jpg"])
        self.client.post(f"/materials/{material_id}/photos/{ninth_id}/delete", data={"_csrf": token})
        self.assertFalse(original_path.exists())
        self.assertEqual(self.client.get(f"/photos/{ninth_id}/preview").status_code, 404)
        with db_connect(self.db_path) as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM photos").fetchone()[0], 8)
        self.assertEqual(self.client.post(f"/materials/{material_id}/packets/{packet_id}/photos/delete-all",
                          data={"_csrf": token}).status_code, 400)
        self.client.post(f"/materials/{material_id}/packets/{packet_id}/photos/delete-all",
                         data={"_csrf": token, "confirm": "all"})
        with db_connect(self.db_path) as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM photos").fetchone()[0], 0)
            self.assertEqual(db.execute("SELECT COUNT(*) FROM material_packets").fetchone()[0], 1)
        self.assertIn(b"did", self.client.get(f"/materials/{material_id}").data)

    def test_invited_reader_cannot_delete_packet_photos(self):
        material_id = self.make_material()
        with db_connect(self.db_path) as db:
            photo = db.execute("SELECT id, packet_id, original_path FROM photos").fetchone()
            photo_id, packet_id, original_path = photo["id"], photo["packet_id"], Path(photo["original_path"])
        token = csrf_from(self.client.get("/"))
        self.client.post("/logout", data={"_csrf": token})
        self.login("reader", "reader-password-123")
        token = csrf_from(self.client.get(f"/materials/{material_id}"))
        self.assertEqual(self.client.post(f"/materials/{material_id}/photos/{photo_id}/delete",
                         data={"_csrf": token}).status_code, 403)
        self.assertEqual(self.client.post(f"/materials/{material_id}/packets/{packet_id}/photos/delete-all",
                         data={"_csrf": token, "confirm": "all"}).status_code, 403)
        self.assertTrue(original_path.exists())

    def test_week_contains_multiple_lessons_and_can_move_them(self):
        material_id = self.make_material()
        token = csrf_from(self.client.get("/"))
        self.client.post("/weeks/new", data={"_csrf": token})
        token = csrf_from(self.client.get("/materials/new?week_number=1"))
        self.client.post("/materials/new", data={"_csrf": token, "kind": "lesson", "week_number": "1",
            "title": "Second lesson", "study_date": "2026-10-07", "content": "Notes"})
        self.assertIn(b"Second lesson", self.client.get("/weeks/1").data)
        self.assertIn(b"Verb practice", self.client.get("/weeks/1").data)
        token = csrf_from(self.client.get(f"/materials/{material_id}/edit"))
        self.client.post(f"/materials/{material_id}/edit", data={
            "_csrf": token, "title": "Verb practice", "study_date": "2026-10-07",
            "week_number": "2", "content": "## Verbs\nI walk to school."})
        self.assertIn(b"Verb practice", self.client.get("/weeks/2").data)
        self.assertNotIn(b"Verb practice", self.client.get("/weeks/1").data)

    def test_csrf_and_escaped_export(self):
        material_id = self.make_material()
        self.assertEqual(self.client.post(f"/materials/{material_id}/comments", data={"body": "bad"}).status_code, 400)
        token = csrf_from(self.client.get(f"/materials/{material_id}/edit"))
        self.client.post(f"/materials/{material_id}/edit", data={
            "_csrf": token, "title": "Verb practice", "study_date": "2026-10-07",
            "week_number": "1", "content": "## <script>alert(1)</script>"})
        exported = self.client.get(f"/materials/{material_id}/export.html")
        self.assertEqual(exported.status_code, 200)
        self.assertIn(b"&lt;script&gt;", exported.data)
        self.assertNotIn(b"<script>", exported.data)

    def test_exam_reviews_previous_week_and_tracks_difficulty_independently(self):
        self.make_material()
        token = csrf_from(self.client.get("/"))
        self.client.post("/weeks/new", data={"_csrf": token})
        token = csrf_from(self.client.get("/materials/new?week_number=2&kind=exam"))
        response = self.client.post("/materials/new", data={"_csrf": token, "kind": "exam", "week_number": "2",
            "exam_for_week": "1", "title": "Week 1 test", "study_date": "2026-10-14", "content": "handwritten answer"}, follow_redirects=True)
        self.assertIn(b"Week 1 test", response.data)
        with db_connect(self.db_path) as db:
            exam_id = db.execute("SELECT id FROM materials WHERE kind = 'exam'").fetchone()["id"]
        token = csrf_from(self.client.get(f"/materials/{exam_id}/analysis"))
        self.client.post(f"/materials/{exam_id}/exam-items/new", data={"_csrf": token, "prompt": "Past tense of walk?", "topic": "past tense"})
        with db_connect(self.db_path) as db:
            item_id = db.execute("SELECT id FROM exam_items").fetchone()["id"]
        token = csrf_from(self.client.get(f"/materials/{exam_id}/analysis"))
        self.client.post(f"/exam-items/{item_id}/review", data={"_csrf": token, "status": "correct", "difficult": "1", "prompt": "Past tense of walk?", "topic": "past tense"})
        with db_connect(self.db_path) as db:
            row = db.execute("SELECT status, difficult FROM exam_items WHERE id = ?", (item_id,)).fetchone()
        self.assertEqual((row["status"], row["difficult"]), ("correct", 1))
        self.assertIn(b"Week 1 test", self.client.get("/weeks/2").data)

    def test_exam_ai_suggestion_requires_review_and_weakness_uses_prior_lesson(self):
        self.make_material()
        token = csrf_from(self.client.get("/"))
        self.client.post("/weeks/new", data={"_csrf": token})
        image = Image.new("RGB", (40, 30), "white")
        output = io.BytesIO()
        image.save(output, "JPEG")
        output.seek(0)
        token = csrf_from(self.client.get("/materials/new?week_number=2&kind=exam"))
        self.client.post("/materials/new", data={"_csrf": token, "kind": "exam", "week_number": "2",
            "exam_for_week": "1", "title": "Test", "study_date": "2026-10-14", "photos": (output, "exam.jpg")},
            content_type="multipart/form-data")
        with db_connect(self.db_path) as db:
            exam_id = db.execute("SELECT id FROM materials WHERE kind = 'exam'").fetchone()["id"]
        token = csrf_from(self.client.get(f"/materials/{exam_id}"))
        with patch("app.call_ai", return_value={"title": "Test", "content": "written walkt", "items": [{
            "prompt": "Past tense?", "submitted_answer": "walkt", "expected_answer": "walked",
            "suggested_status": "incorrect", "topic": "past tense", "note": "spelling"}]}):
            self.client.post(f"/materials/{exam_id}/analyze", data={"_csrf": token})
        with db_connect(self.db_path) as db:
            row = db.execute("SELECT * FROM exam_items WHERE exam_id = ?", (exam_id,)).fetchone()
            self.assertEqual((row["suggested_status"], row["status"]), ("incorrect", "unreviewed"))
            item_id = row["id"]
        token = csrf_from(self.client.get(f"/materials/{exam_id}/analysis"))
        self.client.post(f"/exam-items/{item_id}/review", data={"_csrf": token, "status": "incorrect",
            "prompt": "Past tense?", "topic": "past tense", "submitted_answer": "walkt", "expected_answer": "walked"})
        with patch("app.call_ai", return_value={"report": "과거형 철자를 복습하세요."}) as mocked:
            token = csrf_from(self.client.get(f"/materials/{exam_id}/analysis"))
            result = self.client.post(f"/materials/{exam_id}/weaknesses/generate", data={"_csrf": token}, follow_redirects=True)
        self.assertIn("과거형 철자".encode(), result.data)
        self.assertIn("I walk to school", mocked.call_args.args[0][0]["text"])

    def test_question_feedback_reaches_next_generation(self):
        material_id = self.make_material()
        token = csrf_from(self.client.get(f"/materials/{material_id}"))
        self.client.post(f"/materials/{material_id}/questions/new", data={
            "_csrf": token, "prompt": "Old question", "answer": "Old answer"})
        with db_connect(self.db_path) as db:
            question_id = db.execute("SELECT id FROM questions").fetchone()["id"]
        token = csrf_from(self.client.get(f"/questions/{question_id}/edit"))
        self.client.post(f"/questions/{question_id}/edit", data={
            "_csrf": token, "kind": "빈칸", "prompt": "Old question", "answer": "Old answer",
            "feedback": "문맥을 묻는 문제를 더 만들어 줘"})
        with patch("app.call_ai", return_value={"questions": [{"kind": "문맥", "prompt": "New question",
            "answer": "New answer", "explanation": "Because."}]}) as mocked:
            token = csrf_from(self.client.get(f"/materials/{material_id}"))
            response = self.client.post(f"/materials/{material_id}/questions/generate",
                                        data={"_csrf": token}, follow_redirects=True)
        self.assertIn(b"New question", response.data)
        self.assertIn("문맥을 묻는 문제", mocked.call_args.args[0][0]["text"])

    def test_photo_analysis_creates_reviewable_content(self):
        material_id = self.make_material()
        token = csrf_from(self.client.get(f"/materials/{material_id}"))
        with patch("app.call_ai", return_value={"title": "Past tense", "content": "## Grammar\nI walked home."}) as mocked:
            response = self.client.post(f"/materials/{material_id}/analyze",
                                        data={"_csrf": token}, follow_redirects=True)
        self.assertIn(b"Past tense", response.data)
        self.assertIn(b"I walked home.", response.data)
        self.assertEqual(mocked.call_args.args[0][-1]["type"], "input_image")
        self.assertTrue(mocked.call_args.args[0][-1]["image_url"].startswith("data:image/jpeg;base64,"))
        self.assertIn(b"/materials/1/edit", response.data)

    def test_owner_invites_and_revokes_reader(self):
        material_id = self.make_material()
        token = csrf_from(self.client.get("/invites"))
        invited = self.client.post("/invites", data={
            "_csrf": token, "username": "friend", "display_name": "친구"})
        self.assertEqual(invited.status_code, 200)
        password = re.search(rb"<code>([^<]+)</code>", invited.data).group(1).decode()
        with db_connect(self.db_path) as db:
            user_id = db.execute("SELECT id FROM users WHERE username = 'friend'").fetchone()["id"]
        token = csrf_from(invited)
        self.client.post("/logout", data={"_csrf": token})
        self.login("friend", password)
        self.assertEqual(self.client.get(f"/materials/{material_id}").status_code, 200)
        self.assertEqual(self.client.get("/invites").status_code, 403)
        token = csrf_from(self.client.get("/"))
        self.client.post("/logout", data={"_csrf": token})
        self.login("owner", "owner-password-123")
        token = csrf_from(self.client.get("/invites"))
        self.client.post(f"/invites/{user_id}/revoke", data={"_csrf": token})
        token = csrf_from(self.client.get("/"))
        self.client.post("/logout", data={"_csrf": token})
        self.login("friend", password)
        self.assertEqual(self.client.get(f"/materials/{material_id}").status_code, 200)

    def test_vocabulary_from_material_translation_edit_and_reader_access(self):
        material_id = self.make_material()
        token = csrf_from(self.client.get(f"/materials/{material_id}"))
        created = self.client.post("/vocabulary/new", data={"_csrf": token, "material_id": str(material_id),
            "kind": "sentence", "expression": "I look forward to seeing you.", "note": "수업 중 어려웠음"}, follow_redirects=True)
        self.assertIn(b"I look forward to seeing you.", created.data)
        self.assertIn("1주차".encode(), created.data)
        with db_connect(self.db_path) as db:
            entry_id = db.execute("SELECT id FROM vocabulary").fetchone()["id"]
        token = csrf_from(self.client.get("/vocabulary"))
        deepl_result = io.BytesIO('{"translations":[{"text":"만나 뵙기를 기대합니다."}]}'.encode())
        with patch.dict("os.environ", {"DEEPL_API_KEY": "test-key:fx"}), patch("app.urllib.request.urlopen", return_value=deepl_result) as mocked:
            translated = self.client.post(f"/vocabulary/{entry_id}/translate", data={"_csrf": token}, follow_redirects=True)
        self.assertIn("만나 뵙기를 기대합니다.".encode(), translated.data)
        api_request = mocked.call_args.args[0]
        self.assertEqual(api_request.full_url, "https://api-free.deepl.com/v2/translate")
        self.assertEqual(api_request.get_header("Authorization"), "DeepL-Auth-Key test-key:fx")
        self.assertIn(b'I look forward to seeing you.', api_request.data)
        token = csrf_from(self.client.get("/vocabulary"))
        self.client.post(f"/vocabulary/{entry_id}/edit", data={"_csrf": token, "kind": "sentence",
            "expression": "I look forward to seeing you.", "translation": "만나기를 기대해요.", "note": "직접 수정"})
        self.assertIn("만나기를 기대해요.".encode(), self.client.get("/vocabulary?q=seeing").data)
        self.assertNotIn(b"I look forward", self.client.get("/vocabulary?q=absent").data)
        token = csrf_from(self.client.get("/vocabulary"))
        self.client.post("/logout", data={"_csrf": token})
        self.assertEqual(self.client.get("/vocabulary").status_code, 200)
        self.login("reader", "reader-password-123")
        self.assertIn("만나기를 기대해요.".encode(), self.client.get("/vocabulary").data)
        token = csrf_from(self.client.get("/vocabulary"))
        self.assertEqual(self.client.post("/vocabulary/new", data={"_csrf": token,
            "kind": "word", "expression": "hello"}).status_code, 403)

    def test_public_pages_and_private_attempt_history(self):
        material_id = self.make_material()
        token = csrf_from(self.client.get(f"/materials/{material_id}/practice"))
        self.client.post(f"/materials/{material_id}/questions/new", data={
            "_csrf": token, "prompt": "Past tense of walk?", "answer": "walked"})
        with db_connect(self.db_path) as db:
            question_id = db.execute("SELECT id FROM questions").fetchone()["id"]
        token = csrf_from(self.client.get(f"/materials/{material_id}/practice"))
        saved = self.client.post(f"/materials/{material_id}/practice/attempts", data={
            "_csrf": token, f"answer_{question_id}": "walkt",
            f"status_{question_id}": "incorrect", f"difficult_{question_id}": "1"}, follow_redirects=True)
        self.assertIn(b"walkt", saved.data)
        self.assertIn(b"walked", saved.data)
        self.assertIn("다시 볼 문제".encode(), self.client.get("/progress").data)
        with db_connect(self.db_path) as db:
            attempt = db.execute("SELECT id FROM practice_attempts").fetchone()["id"]
            answer = db.execute("SELECT * FROM practice_answers").fetchone()
            self.assertEqual((answer["status"], answer["difficult"]), ("incorrect", 1))
        with patch("app.call_ai", return_value={"questions": [{"kind": "grammar", "prompt": "Try again",
            "answer": "walked", "explanation": "Past tense"}]}) as mocked:
            token = csrf_from(self.client.get(f"/materials/{material_id}/practice"))
            self.client.post(f"/materials/{material_id}/questions/generate", data={"_csrf": token})
        self.assertIn("walkt", mocked.call_args.args[0][0]["text"])
        self.assertIn("walked", mocked.call_args.args[0][0]["text"])
        token = csrf_from(self.client.get("/"))
        self.client.post("/logout", data={"_csrf": token})
        for path in ("/", "/weeks/1", f"/materials/{material_id}",
                     f"/materials/{material_id}/practice", "/vocabulary"):
            self.assertEqual(self.client.get(path).status_code, 200)
        self.assertEqual(self.client.get("/progress").status_code, 302)
        self.assertEqual(self.client.get(f"/practice/attempts/{attempt}").status_code, 302)
        token = csrf_from(self.client.get("/login"))
        self.assertEqual(self.client.post(f"/materials/{material_id}/practice/attempts",
                                          data={"_csrf": token}).status_code, 302)

    def test_owner_can_store_api_key_without_displaying_it(self):
        self.login("owner", "owner-password-123")
        token = csrf_from(self.client.get("/settings"))
        key = "sk-test-key-for-local-check"
        result = self.client.post("/settings/openai-key", data={"_csrf": token,
            "openai_api_key": key}, follow_redirects=True)
        self.assertIn("키 상태: 저장됨".encode(), result.data)
        self.assertNotIn(key.encode(), result.data)
        key_file = Path(self.app.instance_path) / "openai.key"
        self.assertEqual(key_file.read_text(), key)
        self.assertEqual(key_file.stat().st_mode & 0o777, 0o600)
        token = csrf_from(self.client.get("/settings"))
        self.client.post("/logout", data={"_csrf": token})
        self.assertEqual(self.client.get("/settings").status_code, 302)

    def test_instructors_separate_same_week_and_question_guidance(self):
        first_id = self.make_material()
        token = csrf_from(self.client.get("/settings"))
        self.client.post("/instructors/new", data={"_csrf": token, "name": "월요일 강사",
            "question_guidance": "영작 중심"})
        token = csrf_from(self.client.get("/settings"))
        self.client.post("/instructors/new", data={"_csrf": token, "name": "수요일 강사",
            "question_guidance": "빈칸 중심"})
        with db_connect(self.db_path) as db:
            monday = db.execute("SELECT id FROM instructors WHERE name = '월요일 강사'").fetchone()["id"]
            wednesday = db.execute("SELECT id FROM instructors WHERE name = '수요일 강사'").fetchone()["id"]
        token = csrf_from(self.client.get(f"/materials/{first_id}/edit"))
        self.client.post(f"/materials/{first_id}/edit", data={"_csrf": token, "title": "Monday lesson",
            "study_date": "2026-10-05", "week_number": "1", "content": "I walk to school.",
            "instructor_id": str(monday)})
        token = csrf_from(self.client.get("/materials/new?week_number=1"))
        self.client.post("/materials/new", data={"_csrf": token, "kind": "lesson",
            "week_number": "1", "title": "Wednesday lesson", "study_date": "2026-10-07",
            "content": "I study at home.", "instructor_id": str(wednesday)})
        page = self.client.get("/weeks/1")
        self.assertIn("월요일 강사".encode(), page.data)
        self.assertIn("수요일 강사".encode(), page.data)
        self.assertIn(b"Monday lesson", page.data)
        self.assertIn(b"Wednesday lesson", page.data)
        with db_connect(self.db_path) as db:
            second_id = db.execute("SELECT id FROM materials WHERE title = 'Wednesday lesson'").fetchone()["id"]
        token = csrf_from(self.client.get(f"/materials/{first_id}/practice"))
        self.client.post(f"/materials/{first_id}/questions/new", data={"_csrf": token,
            "prompt": "Old Monday question", "answer": "Monday answer"})
        with db_connect(self.db_path) as db:
            question_id = db.execute("SELECT id FROM questions WHERE material_id = ?", (first_id,)).fetchone()["id"]
        token = csrf_from(self.client.get(f"/questions/{question_id}/edit"))
        self.client.post(f"/questions/{question_id}/edit", data={"_csrf": token, "kind": "grammar",
            "prompt": "Old Monday question", "answer": "Monday answer", "feedback": "월요일 방식"})
        with patch("app.call_ai", return_value={"questions": [{"kind": "grammar", "prompt": "New question",
            "answer": "New answer", "explanation": "Because"}]}) as mocked:
            token = csrf_from(self.client.get(f"/materials/{second_id}/practice"))
            self.client.post(f"/materials/{second_id}/questions/generate", data={"_csrf": token})
        prompt = mocked.call_args.args[0][0]["text"]
        self.assertIn("빈칸 중심", prompt)
        self.assertNotIn("월요일 방식", prompt)

    def test_paid_api_is_disabled_by_default_even_with_key(self):
        from app import call_ai, translation_provider
        from flask import g
        with self.app.test_request_context("/"), patch("app.openai_api_key", return_value="sk-test"), patch.dict("os.environ", {"DEEPL_API_KEY": ""}):
            g.app_db_path = self.db_path
            self.assertIsNone(translation_provider())
            with self.assertRaisesRegex(RuntimeError, "추가 과금"):
                call_ai([], {}, "test", "test")

    def test_plus_plan_uses_separate_token_path_while_paid_api_is_off(self):
        import json
        from app import ai_ready, call_ai, paid_ai_ready

        credential = Path(self.app.instance_path) / "chatgpt-plan.json"
        credential.write_text(json.dumps({"scopes": ["chatgpt.tokens.use.direct"], "refresh_token": "test-refresh"}))
        with self.app.test_request_context("/"), patch("app.call_plan_ai", return_value=({"ok": True}, {"input_tokens": 2}, "gpt-6.1-sol")) as plan_call:
            self.assertFalse(paid_ai_ready())
            self.assertTrue(ai_ready())
            result, usage = call_ai([], {}, "test", "test", include_usage=True)
        self.assertEqual(result, {"ok": True})
        self.assertEqual(usage["input_tokens"], 2)
        plan_call.assert_called_once()

    def test_page_crops_use_valid_image_data_urls(self):
        import base64
        import json

        self.make_material()
        credential = Path(self.app.instance_path) / "chatgpt-plan.json"
        credential.write_text(json.dumps({"scopes": ["chatgpt.tokens.use.direct"], "refresh_token": "test-refresh"}))
        with db_connect(self.db_path) as db:
            photo_id = db.execute("SELECT id FROM photos").fetchone()["id"]
        token = csrf_from(self.client.get(f"/materials/1/read"))
        result = {"title": "Test", "blocks": [{"kind": "text", "text": "Test", "explanation": "", "uncertain": False}]}
        with patch("app.call_ai", return_value=(result, {"input_tokens": 1, "output_tokens": 1})) as mocked:
            response = self.client.post(f"/photos/{photo_id}/render/ai", data={"_csrf": token})
        self.assertEqual(response.status_code, 302)
        images = mocked.call_args.args[0][1:]
        self.assertEqual(len(images), 4)
        for image in images:
            prefix, encoded = image["image_url"].split(",", 1)
            self.assertEqual(prefix, "data:image/jpeg;base64")
            self.assertTrue(base64.b64decode(encoded).startswith(b"\xff\xd8"))


if __name__ == "__main__":
    unittest.main()
