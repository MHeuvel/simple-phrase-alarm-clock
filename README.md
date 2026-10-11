# Simple Phrase alarm clock

Set and delete alarms on a [Kiosk Satellite](https://github.com/jxlarrea/kiosk-satellite)
by voice, **without an LLM**, using a small fixed set of phrases that works with the
**Speech-to-Phrase** add-on.

Home Assistant has no alarm intent, and the built-in conversation agent cannot fill in a
time. This integration adds one: the sentences, the intent handling and the calls to the
kiosk.

**Version 0.2.0.** Early version, built for personal use and shared as is.

## What you can say

| Say | Result |
|---|---|
| "set an alarm for 15 hours 10 minutes" | one-time alarm at 15:10 |
| "set an alarm for 15 hours" | one-time alarm at 15:00 |
| "set a repeating alarm for 7 hours 30 minutes on monday" | alarm every Monday at 07:30 |
| "set a repeating alarm for 7 hours on monday" | alarm every Monday at 07:00 |
| "delete the last alarm" | deletes the alarm that was set last on that kiosk |
| "delete the alarm for 15 hours 10 minutes" | deletes the one-time alarm at 15:10 |
| "delete the alarm for 15 hours" | deletes the one-time alarm at 15:00 |
| "show the alarm list" or "display all alarms" | opens the alarm list on the kiosk |
| "close the alarm list" or "hide the alarms" | closes the alarm list |

The set is deliberately small. Speech-to-Phrase only understands phrases it was trained
on, and every optional word or synonym multiplies the number of phrases.

Say it exactly like this, with "hours" and "minutes", also for 1 ("1 hours 1 minutes").
Hours are 0-23 (24-hour clock), minutes 0-59. Weekdays are monday to sunday.

Good to know:

- A **one-time alarm** rings once, switches itself off and stays in the kiosk's list.
  Setting the same time again switches it back on.
- A **repeating alarm** rings every week on that day until you remove it. "Delete the last
  alarm" removes it right after you set it; later, remove it from the alarm list on the
  kiosk ("show the alarm list").
- Deleting **by time** only works for one-time alarms made by this integration. Alarms you
  made by hand on the kiosk are never touched.

## Requirements

- Home Assistant **2025.8 or newer** (developed against 2026.10). The icons need 2026.3.
- Kiosk Satellite with remote administration turned on (default port 2324) and an admin
  password.
- The **Speech-to-Phrase** add-on as the speech-to-text engine of your Assist pipeline.
- **Home Assistant OS** for the automatic Speech-to-Phrase handling (see below). On other
  installation types the integration still works for typed sentences and for speech
  engines that need no training, but you must add the sentences to your recogniser
  yourself.

## Install

1. Add this repository to HACS as a custom repository (category **Integration**):

   [![Add to HACS](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=MHeuvel&repository=simple-phrase-alarm-clock&category=integration)

   Or add `https://github.com/MHeuvel/simple-phrase-alarm-clock` by hand under
   HACS -> Custom repositories.
2. Download **Simple Phrase alarm clock** and restart Home Assistant.
3. Go to Settings -> Devices & services -> Add integration ->
   **Simple Phrase alarm clock**.
4. Choose the voice satellite (the `assist_satellite` entity of the device the kiosk runs
   on), then enter the kiosk's host or IP address, port and admin password.

Add one entry per kiosk.

The password is used once to get a long-lived token (valid 10 years) and is **not
stored**; only the token is. The kiosk's tokens are stateless: changing the admin password
does not revoke an issued token, and neither does removing this integration. Treat the
token like a password. If the kiosk ever rejects it, Home Assistant asks for the password
again.

HTTP is the kiosk's default and is meant for a trusted LAN. If you turned on HTTPS with a
self-signed certificate, tick *Use HTTPS* and untick *Verify the HTTPS certificate*.

## How it works

- The alarm goes to **the kiosk you spoke to**: the integration matches the voice
  satellite that heard you to the kiosk you linked it to. There is one sentence set for
  all kiosks. A sentence typed in the Assist dialog has no satellite, so it only works when
  exactly one kiosk is configured.
- Alarm ids are derived from the time, with a fixed prefix: `spac-1510` for a one-time
  alarm and `spac-0730-1` for a repeating alarm on Monday. Setting the same alarm again
  changes the same alarm, so this integration never creates duplicates.
- The integration keeps one small piece of state: the last alarm it set per kiosk, so that
  "delete the last alarm" works. The kiosk itself is the source of truth for all alarms.

## What it writes (and where)

One sentence definition is written to two places:

| File | Read by | Handling |
|---|---|---|
| `/config/custom_sentences/en/simple_phrase_alarm_clock.yaml` | Assist | owned by the integration, overwritten when it changes |
| `/share/speech-to-phrase/custom_sentences/en/sentences.yaml` | Speech-to-Phrase | **merged**: only our intents and lists are added or replaced, everything else in the file is kept |

- When a file changes, the previous version is kept next to it as a timestamped `*.bak`.
  Nothing is overwritten without a copy.
- When the Speech-to-Phrase file changed, the add-on is **restarted** so it trains on the
  new phrases (add-on slug `core_speech-to-phrase` by default). Nothing is restarted when
  nothing changed. If a restart is not possible you get a notification asking you to do
  it yourself. Training can take a while; voice commands work again once it is ready.
- If `/share` does not exist (not Home Assistant OS) or the Speech-to-Phrase file cannot be
  parsed, that file is left alone.
- Removing the last kiosk removes what was generated.

Because the same sentences must not be handled twice, do not keep another intent or
custom sentence file for the same phrases.

## Options

On the integration: turn the Speech-to-Phrase handling off, or change the add-on slug.
Options are shared by all kiosks; the first one added decides.

## Troubleshooting

- **Nothing happens by voice, but typing works:** check that your pipeline uses
  Speech-to-Phrase, and that the add-on finished training (see its log).
- **"This voice assistant has no alarm clock set up":** the satellite entity you linked is
  not the one that heard you.
- **"There is already an alarm for ...":** an alarm made by hand on the kiosk rings at that
  time (and on the same days). Delete it there or choose another time.

For the raw replies of the kiosk, enable debug logging:

```yaml
logger:
  logs:
    custom_components.simple_phrase_alarm_clock: debug
```

## License and credits

MIT License, see `LICENSE`.

Not affiliated with Home Assistant or Kiosk Satellite. Kiosk Satellite is made by
[jxlarrea](https://github.com/jxlarrea/kiosk-satellite).
