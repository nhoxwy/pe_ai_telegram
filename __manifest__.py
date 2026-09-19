{
    "name": "Pe AI Telegram Gateway",
    "version": "18.0.1.0.0",
    "category": "Tools",
    "summary": "Telegram gateway for Pe AI Core",
    "depends": ["pe_ai_core"],
    "data": [
        "security/ir.model.access.csv",
        "views/telegram_config_views.xml",
        "views/telegram_menu.xml",
        "data/ir_cron.xml",
    ],
    "installable": True,
    "application": False,
    "license": "LGPL-3",
}
