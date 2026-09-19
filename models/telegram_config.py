import json
import urllib.parse
import urllib.request

from odoo import api, fields, models
from odoo.exceptions import UserError

class PeAITelegramConfig(models.Model):
    _name = "pe.ai.telegram.config"
    _description = "Pe AI Telegram Configuration"

    name = fields.Char(default="Pe AI Telegram", required=True)
    active = fields.Boolean(default=True)
    bot_token = fields.Char(string="Bot Token", password=True)
    owner_chat_id = fields.Char(string="Owner Chat ID")
    polling_enabled = fields.Boolean(default=True)
    last_update_id = fields.Integer(default=0)

    @api.model
    def get_config(self):
        config = self.search([("active", "=", True)], limit=1)
        return config

    def _api(self, method, params=None):
        self.ensure_one()
        if not self.bot_token:
            raise UserError("Chưa nhập Telegram Bot Token.")
        url = "https://api.telegram.org/bot%s/%s" % (self.bot_token, method)
        data = urllib.parse.urlencode(params or {}).encode("utf-8")
        req = urllib.request.Request(url, data=data, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=30) as response:
                result = json.loads(response.read().decode("utf-8"))
        except Exception as exc:
            raise UserError("Telegram API error: %s" % exc)
        if not result.get("ok"):
            raise UserError("Telegram API error: %s" % result.get("description", result))
        return result.get("result")

    def action_test_connection(self):
        self.ensure_one()
        result = self._api("getMe")
        raise UserError("Kết nối OK: @%s (id=%s)" % (result.get("username"), result.get("id")))

    def action_detect_owner(self):
        self.ensure_one()
        updates = self._api("getUpdates", {
            "limit": 20,
            "timeout": 0,
            "allowed_updates": json.dumps(["message"]),
        })
        private_chats = []
        for update in updates or []:
            message = update.get("message") or {}
            chat = message.get("chat") or {}
            if chat.get("type") == "private" and chat.get("id") is not None:
                private_chats.append((str(chat["id"]), message.get("text", "")))
        if not private_chats:
            raise UserError("Chưa thấy tin nhắn private. Hãy mở bot trên Telegram và gửi /start trước.")
        chat_id, text = private_chats[-1]
        self.owner_chat_id = chat_id
        self.last_update_id = max([u.get("update_id", 0) for u in updates or []] + [self.last_update_id])
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": "Pe AI Telegram",
                "message": "Đã nhận diện Owner Chat ID: %s" % chat_id,
                "type": "success",
                "sticky": False,
            },
        }

    def send_message(self, chat_id, text):
        self.ensure_one()
        # Telegram sendMessage accepts max 4096 chars.
        chunks = [text[i:i+4000] for i in range(0, len(text or ""), 4000)] or [""]
        for chunk in chunks:
            self._api("sendMessage", {"chat_id": chat_id, "text": chunk})

    def process_updates(self):
        self.ensure_one()
        if not self.polling_enabled or not self.bot_token or not self.owner_chat_id:
            return 0

        updates = self._api("getUpdates", {
            "offset": self.last_update_id + 1,
            "limit": 100,
            "timeout": 0,
            "allowed_updates": json.dumps(["message"]),
        })
        processed = 0
        Service = self.env["pe.ai.service"].sudo()
        Conversation = self.env["pe.ai.conversation"].sudo()
        Message = self.env["pe.ai.message"].sudo()

        for update in updates or []:
            self.last_update_id = max(self.last_update_id, update.get("update_id", 0))
            message = update.get("message") or {}
            chat = message.get("chat") or {}
            text = message.get("text")
            if chat.get("type") != "private" or not text:
                continue
            if str(chat.get("id")) != str(self.owner_chat_id):
                continue

            conversation = Conversation.search([
                ("channel", "=", "telegram"),
                ("external_chat_id", "=", str(chat.get("id"))),
                ("active", "=", True),
            ], limit=1)
            if not conversation:
                conversation = Conversation.create({
                    "name": "Owner Telegram",
                    "channel": "telegram",
                    "external_chat_id": str(chat.get("id")),
                })

            Message.create({
                "conversation_id": conversation.id,
                "role": "user",
                "body": text,
                "external_message_id": str(message.get("message_id")),
            })

            if text.strip() == "/start":
                reply = (
                    "Xin chào! Tôi là Pe AI.\n\n"
                    "Đây là cổng Telegram dành cho chủ shop. "
                    "Bạn có thể hỏi tôi, sau này có thể dùng tôi để cập nhật Knowledge."
                )
            else:
                try:
                    reply = Service.process_owner_message(conversation, text)
                except Exception as exc:
                    reply = "Pe AI gặp lỗi: %s" % exc

            Message.create({
                "conversation_id": conversation.id,
                "role": "assistant",
                "body": reply,
            })
            self.send_message(str(chat.get("id")), reply)
            processed += 1

        self.env.cr.commit()
        return processed
