"""Constants for Simple Phrase alarm clock.

This module must stay free of Home Assistant imports so the pure-logic
modules (sentences, files, alarm) can be unit tested without Home Assistant.
"""

DOMAIN = "simple_phrase_alarm_clock"

# Config entry data
CONF_SATELLITE = "satellite_entity_id"

# Options (stored on the config entry, read from the first entry)
CONF_MANAGE_S2P = "manage_speech_to_phrase"
CONF_S2P_ADDON = "speech_to_phrase_addon"

DEFAULT_PORT = 2324
DEFAULT_S2P_ADDON = "core_speech-to-phrase"

# Only English in v1.
LANGUAGE = "en"

# Slot (list) names. Prefixed so they never collide with lists in other
# custom sentence files, for example in the Speech-to-Phrase sentences.yaml.
SLOT_HOURS = "spac_hours"
SLOT_MINUTES = "spac_minutes"
# The repeating alarm has its own minutes list, so it can be thinned out
# (for example to steps of five) without touching the one-time alarm.
SLOT_REPEAT_MINUTES = "spac_rminutes"
SLOT_WEEKDAY = "spac_weekday"  # 0 = Sunday ... 6 = Saturday, as the kiosk expects

# Intent names (global in Home Assistant, so prefixed as well).
INTENT_SET = "SimplePhraseAlarmSet"
INTENT_SET_REPEATING = "SimplePhraseAlarmSetRepeating"
INTENT_DELETE = "SimplePhraseAlarmDelete"
INTENT_SHOW_LIST = "SimplePhraseAlarmShowList"
INTENT_HIDE_LIST = "SimplePhraseAlarmHideList"

# Alarm ids created by this integration always start with this prefix, so
# alarms made by hand on the kiosk are never touched.
ID_PREFIX = "spac"

# File names / locations
CONFIG_SENTENCES_FILENAME = "simple_phrase_alarm_clock.yaml"
S2P_SHARE_ROOT = "/share/speech-to-phrase/custom_sentences"
S2P_SENTENCES_FILENAME = "sentences.yaml"

NOTIFICATION_ID = f"{DOMAIN}_speech_to_phrase"
