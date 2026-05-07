"""
应用显示名称与中文别名覆盖。
"""

from __future__ import annotations

from typing import Any, Dict


APP_DISPLAY_NAME_OVERRIDES: Dict[str, Dict[str, Any]] = {
    "com.apple.ActivityMonitor": {
        "display_name": "活动监视器",
        "aliases": ["活动监视器"],
    },
    "com.apple.apps.launcher": {
        "display_name": "应用程序",
        "aliases": ["应用程序"],
    },
    "com.apple.AppStore": {
        "display_name": "应用商店",
        "aliases": ["应用商店"],
    },
    "com.apple.AddressBook": {
        "display_name": "通讯录",
        "aliases": ["通讯录"],
    },
    "com.apple.Chess": {
        "display_name": "国际象棋",
        "aliases": ["国际象棋"],
    },
    "com.apple.Home": {
        "display_name": "家庭",
        "aliases": ["家庭"],
    },
    "com.apple.Maps": {
        "display_name": "地图",
        "aliases": ["地图"],
    },
    "com.apple.Magnifier": {
        "display_name": "放大器",
        "aliases": ["放大器"],
    },
    "com.apple.MobileSMS": {
        "display_name": "信息",
        "aliases": ["信息"],
    },
    "com.apple.Music": {
        "display_name": "音乐",
        "aliases": ["音乐"],
    },
    "com.apple.Notes": {
        "display_name": "备忘录",
        "aliases": ["备忘录"],
    },
    "com.apple.Passwords": {
        "display_name": "密码",
        "aliases": ["密码"],
    },
    "com.apple.Photos": {
        "display_name": "照片",
        "aliases": ["照片"],
    },
    "com.apple.Preview": {
        "display_name": "预览",
        "aliases": ["预览"],
    },
    "com.apple.shortcuts": {
        "display_name": "快捷指令",
        "aliases": ["快捷指令"],
    },
    "com.apple.stocks": {
        "display_name": "股市",
        "aliases": ["股市"],
    },
    "com.apple.Terminal": {
        "display_name": "终端",
        "aliases": ["终端"],
    },
    "com.apple.TextEdit": {
        "display_name": "文本编辑",
        "aliases": ["文本编辑"],
    },
    "com.apple.helpviewer": {
        "display_name": "提示",
        "aliases": ["提示"],
    },
    "com.apple.TV": {
        "display_name": "视频",
        "aliases": ["视频"],
    },
    "com.apple.VoiceMemos": {
        "display_name": "语音备忘录",
        "aliases": ["语音备忘录"],
    },
    "com.apple.calculator": {
        "display_name": "计算器",
        "aliases": ["计算器"],
    },
    "com.apple.clock": {
        "display_name": "时钟",
        "aliases": ["时钟"],
    },
    "com.apple.Dictionary": {
        "display_name": "词典",
        "aliases": ["词典"],
    },
    "com.apple.findmy": {
        "display_name": "查找",
        "aliases": ["查找"],
    },
    "com.apple.finder": {
        "display_name": "访达",
        "aliases": ["访达"],
    },
    "com.apple.freeform": {
        "display_name": "无边记",
        "aliases": ["无边记"],
    },
    "com.apple.games": {
        "display_name": "游戏",
        "aliases": ["游戏"],
    },
    "com.apple.iCal": {
        "display_name": "日历",
        "aliases": ["日历"],
    },
    "com.apple.iBooksX": {
        "display_name": "图书",
        "aliases": ["图书"],
    },
    "com.apple.journal": {
        "display_name": "手记",
        "aliases": ["手记"],
    },
    "com.apple.mail": {
        "display_name": "邮件",
        "aliases": ["邮件"],
    },
    "com.apple.mobilephone": {
        "display_name": "电话",
        "aliases": ["电话"],
    },
    "com.apple.news": {
        "display_name": "新闻",
        "aliases": ["新闻"],
    },
    "com.apple.podcasts": {
        "display_name": "播客",
        "aliases": ["播客"],
    },
    "com.apple.reminders": {
        "display_name": "提醒事项",
        "aliases": ["提醒事项"],
    },
    "com.apple.systempreferences": {
        "display_name": "系统设置",
        "aliases": ["系统设置"],
    },
    "com.apple.weather": {
        "display_name": "天气",
        "aliases": ["天气"],
    },
    "com.bot.pc.doubao": {
        "display_name": "豆包",
        "aliases": ["豆包"],
    },
    "com.electron.lark": {
        "display_name": "飞书",
        "aliases": ["飞书"],
    },
    "com.volcengine.corplink": {
        "display_name": "飞连",
        "aliases": ["飞连"],
    },
}


def get_app_display_override(identifier: Any) -> Dict[str, Any]:
    normalized = str(identifier or "").strip()
    if not normalized:
        return {}
    return dict(APP_DISPLAY_NAME_OVERRIDES.get(normalized, {}))
