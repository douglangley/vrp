"""Plain-language help for radio settings (VRP-owned, framework-agnostic).

CHIRP drivers expose settings as short identifiers — ``tot``, ``abr``, ``ste``,
``scode`` — whose meaning is obvious only if you already know the radio. A
sighted user can reach for the manual beside the window; a screen-reader user
gets the bare field name and nothing else. This module supplies the missing
sentence.

Two sources, in priority order:

1. **The driver's own text.** A few CHIRP drivers call ``RadioSetting.set_doc``
   (upstream started adding these for the UV-5R and QYT KT-8900 in July 2026).
   That text is written for that exact radio, so it always wins.
2. **This table.** Keyed by a *normalized* name, because the same feature is
   spelled many ways across 312 drivers: ``beep`` / ``settings.beep``,
   ``tot`` / ``timeouttimer``, ``vox`` / ``voxlevel`` / ``settings.vox``.

Deliberately **not** covered: table-row fields such as DTMF code lists, FM
presets, and 2-tone entries. They are the largest share of the ~35,000 settings
in the pinned corpus, but they are data rows rather than features, and generic
prose about them would be padding at best and wrong at worst.

The text describes what a control *generally* does on amateur handhelds and
mobiles. Where behaviour genuinely varies between models it says so rather than
inventing a specific claim, because a confident wrong description is worse than
none. This is why the driver's own text takes priority.

This module must never edit ``chirp/``: that tree is vendored, pinned, and
re-cloned, so help added there would be destroyed by the next CHIRP update.
"""

from __future__ import annotations

import re

# Normalized name -> plain-language description.
HELP: dict[str, str] = {
    # -- audio feedback and prompts ------------------------------------
    "beep": (
        "Sounds a short tone when you press a key, confirming the press "
        "without looking at the radio. Turning it off makes the radio silent "
        "in quiet surroundings."
    ),
    "beepvolume": (
        "How loud the key-press confirmation tone is, independently of the "
        "receive volume."
    ),
    "voice": (
        "Speaks menu items and channel changes aloud. On most radios the "
        "choice is off, English, or the radio's second language."
    ),
    "roger": (
        "Sends a short tone at the end of each transmission, telling the other "
        "station you have finished speaking and released the key."
    ),
    "sidetone": (
        "Plays a tone in your own speaker or earpiece as you send, so you can "
        "hear what is being transmitted."
    ),
    "dtmfst": (
        "Plays the DTMF touch tones in your own speaker as they are sent, so "
        "you can hear the digits going out."
    ),
    "keypadtone": (
        "Sounds a tone when a keypad digit is pressed, separately from the "
        "general key beep."
    ),

    # -- transmit control ----------------------------------------------
    "tot": (
        "Transmit time-out timer. Cuts your transmission off after this many "
        "seconds, so a stuck or accidentally pressed key cannot hold the "
        "repeater open. Set it off only if you are sure that is safe."
    ),
    "totalert": (
        "Warns you a few seconds before the transmit time-out timer expires, "
        "giving you a chance to unkey and start again."
    ),
    "power": (
        "Transmit power level. Lower power saves the battery and reduces "
        "interference to distant stations; higher power helps reach a weak or "
        "far-away repeater."
    ),
    "bcl": (
        "Busy channel lockout. Prevents transmitting while the radio is "
        "already receiving a signal on that channel, so you do not talk over "
        "someone you can hear."
    ),
    "txstop": (
        "Blocks transmitting entirely, leaving the radio receive-only. Useful "
        "for listening on frequencies you are not licensed to transmit on."
    ),
    "talkaround": (
        "Transmits on the repeater's output frequency instead of its input, "
        "letting you talk directly to nearby stations without the repeater."
    ),

    # -- squelch and receive -------------------------------------------
    "squelch": (
        "How strong a received signal must be before the speaker unmutes. 0 "
        "leaves the speaker open and you hear background noise; higher values "
        "silence weak signals along with the noise."
    ),
    "ste": (
        "Squelch tail eliminate. Suppresses the short burst of noise heard "
        "when the other station stops transmitting."
    ),
    "rpste": (
        "Squelch tail eliminate for repeater use. Suppresses the noise burst "
        "at the end of a transmission relayed through a repeater."
    ),
    "pttlt": (
        "How long the radio transmits before your audio starts, giving "
        "repeaters and receivers time to open so your first word is not "
        "clipped."
    ),
    "compander": (
        "Compresses the audio when transmitting and expands it when receiving, "
        "which can lift speech out of the noise. Both radios must have it on."
    ),
    "scrambler": (
        "Inverts the audio so casual listeners hear only noise. It is not "
        "real encryption, and it is not permitted on amateur bands in most "
        "countries."
    ),
    "micgain": (
        "How sensitive the microphone is. Raise it if you are told you sound "
        "quiet, lower it if your audio sounds distorted."
    ),
    "volume": (
        "The receive audio level the radio starts at when it is switched on."
    ),
    "speaker": (
        "Whether audio comes out of the radio's own speaker, or only through "
        "an attached accessory."
    ),
    "earphone": (
        "Routes audio to an attached earpiece or headset instead of the "
        "speaker."
    ),

    # -- VOX -------------------------------------------------------------
    "vox": (
        "Voice-operated transmit: the radio keys up when it hears you speak, "
        "so you do not have to press the transmit key. Higher values need "
        "louder speech to trigger; too high a setting can key the radio on "
        "background noise."
    ),
    "voxdelay": (
        "How long the radio keeps transmitting after you stop speaking, so "
        "short pauses do not drop your transmission."
    ),

    # -- power and battery -----------------------------------------------
    "save": (
        "Battery save. Puts the receiver to sleep briefly between checks for "
        "a signal, extending battery life at the cost of possibly clipping "
        "the first moment of a transmission."
    ),
    "apo": (
        "Automatic power off. Switches the radio off after this long with no "
        "activity, so a bag-packed radio does not flatten its battery."
    ),
    "lowvoltage": (
        "Warns you when the battery is nearly flat, usually with a tone or a "
        "display indicator."
    ),

    # -- display and keys -------------------------------------------------
    "backlight": (
        "How long the display and keypad stay lit after a key press. A "
        "shorter time saves battery; always-on is easier to read."
    ),
    "brightness": (
        "How bright the display backlight is when it is lit. Lower settings "
        "are easier on the eyes at night and use less battery."
    ),
    "contrast": (
        "How strongly the display's text stands out from its background. "
        "Adjust it if the screen looks washed out or too dark."
    ),
    "keylock": (
        "Locks the keypad so buttons cannot be pressed accidentally in a "
        "pocket or bag. The transmit key usually still works."
    ),
    "autolock": (
        "Locks the keypad by itself after a period with no key presses, so it "
        "cannot be nudged in a pocket."
    ),
    "ponmsg": (
        "What the display shows when the radio is switched on — typically a "
        "short message of your choosing, the battery voltage, or the radio's "
        "name."
    ),
    "language": (
        "The language used for the radio's menus and spoken prompts."
    ),
    "workmode": (
        "Whether the radio tunes freely by frequency (VFO mode) or steps "
        "through your stored channels (memory mode)."
    ),
    "display": (
        "What the radio shows for a channel — its name, its frequency, or its "
        "channel number."
    ),
    "menuquit": (
        "How long the radio waits before leaving the menu on its own when you "
        "stop pressing keys."
    ),

    # -- tuning ------------------------------------------------------------
    "step": (
        "How far each tuning click moves in frequency. Match it to the "
        "channel spacing used on the band you are tuning."
    ),
    "offset": (
        "How far the transmit frequency sits from the receive frequency when "
        "working through a repeater. The direction is set separately by "
        "duplex or shift."
    ),
    "wide": (
        "Channel bandwidth. Wide (FM) gives better audio; narrow (NFM) takes "
        "less space and is required on many commercial and newer amateur "
        "channels. It must match the station you are working."
    ),

    # -- scanning ----------------------------------------------------------
    "scanmode": (
        "What the radio does when a scan finds a busy channel: stop there, "
        "pause for a few seconds and carry on, or resume once the signal "
        "disappears."
    ),
    "tdr": (
        "Dual watch. Listens on two channels or bands in turn, so you can "
        "monitor both at once. It usually shortens battery life."
    ),

    # -- signalling --------------------------------------------------------
    "scode": (
        "Which stored PTT-ID code this channel sends to identify your radio "
        "when you key up or unkey."
    ),
    "pttid": (
        "When the radio sends its identifying code — never, when you start "
        "transmitting, when you stop, or both."
    ),
    "ani": (
        "Automatic number identification: the code that identifies your radio "
        "to others on the network."
    ),
    "dtmfon": "How long each DTMF tone is held when the radio sends digits.",
    "dtmfoff": "How long the radio pauses between sent DTMF digits.",
    "dtmfdelay": (
        "How long the radio waits after keying up before sending DTMF digits, "
        "giving the far end time to open."
    ),
    "cwid": (
        "Sends your callsign in Morse code to identify the station "
        "automatically."
    ),
    "alarm": (
        "What the radio does when the emergency alarm is triggered — sound "
        "locally, or also transmit to alert other stations."
    ),

    # -- broadcast radio ---------------------------------------------------
    "fmradio": (
        "The broadcast FM receiver, for listening to ordinary radio stations. "
        "It normally mutes when a signal arrives on your channel."
    ),

    # -- repeater and band behaviour ---------------------------------------
    "ars": (
        "Automatic repeater shift. The radio applies the standard repeater "
        "offset by itself when you tune into a band segment where repeaters "
        "live, so you do not have to set the shift each time."
    ),
    "rfsquelch": (
        "Mutes the speaker until a signal reaches this strength on the meter. "
        "It works alongside the ordinary squelch, letting you ignore signals "
        "that are audible but too weak to be useful."
    ),
    "bandedgebeep": (
        "Sounds a tone when tuning reaches the edge of the band, warning you "
        "before you tune outside it."
    ),
    "bandlimit": (
        "Keeps tuning inside the current band instead of continuing on into "
        "the next one."
    ),

    # -- scanning extras ----------------------------------------------------
    "priorityrevert": (
        "Jumps back to the priority channel whenever a signal appears there, "
        "so you do not miss activity while listening elsewhere."
    ),
    "weatheralert": (
        "Watches the weather channels and alerts you when a warning tone is "
        "broadcast."
    ),
    "smartsearch": (
        "Sweeps the band and collects active frequencies into a temporary "
        "list, for finding activity somewhere unfamiliar."
    ),
    "scanlamp": (
        "Lights the display while scanning, so you can see which channel the "
        "radio stopped on."
    ),
    "bankscan": (
        "Whether this memory bank is included when the radio scans banks, "
        "letting you skip groups you are not interested in."
    ),

    # -- indicators and keys ------------------------------------------------
    "busyled": (
        "Lights an indicator on the radio while a signal is being received."
    ),
    "txled": (
        "Lights an indicator on the radio while it is transmitting."
    ),
    "monikey": (
        "What the monitor key does — hold it to open the squelch and hear "
        "everything on the channel, including signals too weak or wrongly "
        "toned to break squelch normally."
    ),
    "bell": (
        "How many times the radio chimes when a call arrives on a channel "
        "using tone or code squelch."
    ),
    "arts": (
        "Automatic Range Transponder System. Yaesu radios exchange a short "
        "signal periodically and tell you when the other station drifts out "
        "of range."
    ),
    "dcsinverted": (
        "Also accepts the inverted form of the DCS code, which some stations "
        "and repeaters send instead of the normal one."
    ),

    # -- misc --------------------------------------------------------------
    "sidekey": (
        "What the programmable side button does — a short press and a long "
        "press are usually set separately."
    ),
    "reset": (
        "Returns settings to the factory defaults. On many radios this also "
        "erases your stored channels, so save a copy of the image first."
    ),
}

# Spelling variants that mean the same thing, mapped onto a key in HELP.
ALIASES: dict[str, str] = {
    "squelchlevel": "squelch",
    "sql": "squelch",
    "sqlevel": "squelch",
    "voxlevel": "vox",
    "voxgain": "vox",
    "voxsensitivity": "vox",
    "voxd": "voxdelay",
    "voxdly": "voxdelay",
    "voiceprompts": "voice",
    "voiceprompt": "voice",
    "voicesw": "voice",
    "batterysave": "save",
    "anicode": "ani",
    "batterysaver": "save",
    "battsave": "save",
    "bsave": "save",
    "powersave": "save",
    "mdfa": "display",
    "mdfb": "display",
    "displaymode": "display",
    "rptrl": "rpste",
    "rptste": "rpste",
    "autopoweroff": "apo",
    "autopower": "apo",
    "rogerbeep": "roger",
    
    "txtimeout": "tot",
    "timeouttimer": "tot",
    "timeout": "tot",
    "totalarm": "totalert",
    "bcklight": "backlight",
    "abr": "backlight",
    "backlighttime": "backlight",
    "wtled": "backlight",
    "lcdbrightness": "brightness",
    "autolk": "autolock",
    "keyautolock": "autolock",
    "lock": "keylock",
    "keypadlock": "keylock",
    "poweronmsg": "ponmsg",
    "ponmessage": "ponmsg",
    "startupmsg": "ponmsg",
    "vfomr": "workmode",
    "mode": "workmode",
    "tuningstep": "step",
    "stepsize": "step",
    "widenarrow": "wide",
    "bandwidth": "wide",
    "narrow": "wide",
    "channelspacing": "wide",
    "scanresume": "scanmode",
    "screv": "scanmode",
    "scanrev": "scanmode",
    "dw": "tdr",
    "dualwatch": "tdr",
    "dualdisplay": "tdr",
    "busylock": "bcl",
    "busy": "bcl",
    "busychannellockout": "bcl",
    "txpower": "power",
    "powerlevel": "power",
    "mic": "micgain",
    "micleve": "micgain",
    "miclevel": "micgain",
    "squelchtail": "ste",
    "dtmfsidetone": "dtmfst",
    "dtmfspeedon": "dtmfon",
    "dtmfspeedoff": "dtmfoff",
    "fmen": "fmradio",
    "fmfunc": "fmradio",
    "broadcastfm": "fmradio",
    "pf": "sidekey",
    "skey": "sidekey",
    "programmablekey": "sidekey",
    "factoryreset": "reset",
    "batterywarning": "lowvoltage",
    "battwarn": "lowvoltage",
    # Yaesu-style abbreviations (FT-60 and relatives).
    "bclo": "bcl",
    "beepkey": "beep",
    "lamp": "backlight",
    "scnlmp": "scanlamp",
    "rfsql": "rfsquelch",
    "resume": "scanmode",
    "scnmd": "scanmode",
    "rxsave": "save",
    "txsave": "save",
    "prirvt": "priorityrevert",
    "wxalt": "weatheralert",
    "ssrch": "smartsearch",
    "edgbep": "bandedgebeep",
    "vfobnd": "bandlimit",
    "bsyled": "busyled",
    "mtcl": "monikey",
    "moni": "monikey",
    "arbep": "arts",
    "arint": "arts",
    "dcsnr": "dcsinverted",
    "dtdly": "dtmfdelay",
    "dtspd": "dtmfon",
    "mbs": "bankscan",
    "bnkscan": "bankscan",
}


def normalize(name: str) -> str:
    """Reduce a driver's setting identifier to a comparable concept key.

    Drivers spell the same feature many ways and nest it at different depths:
    ``settings.beep``, ``beep``, ``pttid/3.code``, ``vfo.a.freq``. Take the
    final path segment, drop indices and punctuation, and strip a trailing
    number so ``line1`` and ``line2`` land together.
    """
    text = (name or "").strip().lower()
    text = text.split("/")[-1]
    text = text.split(".")[-1]
    text = re.sub(r"[^a-z0-9]+", "", text)
    text = re.sub(r"\d+$", "", text)
    return text


def lookup(name: str) -> str | None:
    """Return VRP's description for a setting identifier, or ``None``."""
    key = normalize(name)
    if not key:
        return None
    key = ALIASES.get(key, key)
    return HELP.get(key)


def help_for(name: str, driver_doc: str | None = None) -> str | None:
    """Best available description for one setting.

    ``driver_doc`` is the driver's own ``RadioSetting`` documentation and always
    wins: it was written for that exact radio, whereas this module's text
    describes the feature in general.
    """
    if driver_doc:
        text = " ".join(str(driver_doc).split())
        if text:
            return text
    return lookup(name)


def coverage(names) -> tuple[int, int]:
    """Return ``(described, total)`` for an iterable of setting names.

    Used by the tests to keep this table honest about how much it actually
    covers, rather than asserting a number that quietly drifts.
    """
    names = list(names)
    return sum(1 for name in names if lookup(name)), len(names)
