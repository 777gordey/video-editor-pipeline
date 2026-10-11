"""Three presets of the batch machine, generalised from the hand-built K3 / K1 / K2 edits.
Hard rules shared by every preset (checked in plan.py / build.py / mix.py):
  * the real room is the ONLY video layer (no cut-out, no replaced background, no overlay on the face);
    full-frame stock is a short cutaway, never a layer under the speaker
  * adult, masculine look: no cartoon stickers / mascots / emoji, no pastel
  * voice untouched in time; music ~11 dB under voice RMS in speech, SFX peak ~10 dB under voice peak, loudnorm -14 LUFS
"""

FONT_FILES = {   # role pattern -> woff2 base (cyrillic + latin subsets are both loaded)
    "oswald600": ("Oswald", 600, "normal", "oswald-{sc}-600-normal"),
    "oswald700": ("Oswald", 700, "normal", "oswald-{sc}-700-normal"),
    "russo": ("Russo One", 400, "normal", "russo-one-{sc}-400-normal"),
    "robotocond": ("Roboto Condensed", 800, "normal", "roboto-condensed-{sc}-800-normal"),
    "manrope": ("Manrope", 800, "normal", "manrope-{sc}-800-normal"),
    "mono": ("JetBrains Mono", 800, "normal", "jetbrains-mono-{sc}-800-normal"),
    "lora": ("Lora", 700, "italic", "lora-{sc}-700-italic"),
    "unbounded": ("Unbounded", 900, "normal", "unbounded-{sc}-900-normal"),
    "rubik": ("Rubik", 800, "normal", "rubik-{sc}-800-normal"),
    "rubikmono": ("Rubik Mono One", 400, "normal", "rubik-mono-one-{sc}-400-normal"),
    "ptserif": ("PT Serif", 700, "italic", "pt-serif-{sc}-700-italic"),
}

COMMON_KINDS = ["punch", "stock", "stat", "stamp"]

PRESETS = {
    "dark": dict(
        id="dark", name="Dark Steel", base_look="K3 (hard editorial, dark moody)",
        css="style_dark.css", fonts=["oswald600", "oswald700", "russo", "robotocond"],
        roles={"base": "oswald600", "key": "robotocond", "emo": "russo", "h1": "oswald700", "h2": "russo", "h3": "robotocond"},
        upper=True, key_mult=1.08, emo_mult=1.05, cap_y=1545, cap_max=96, cap_w=940, gap=0.20, cap_words=5,
        hook_y=(1300, 1465, 1640), hook_size=(120, 150, 128), hook_font_role=("h1", "h2", "h3"),
        grade=("eq=contrast=1.22:saturation=0.50:gamma=0.90,colorbalance=rs=-0.07:gs=-0.01:bs=0.08:rm=-0.06:bm=0.07:rh=-0.03:bh=0.05,"
               "curves=all='0/0 0.12/0.05 0.5/0.47 0.9/0.95 1/1',noise=alls=6:allf=t"),
        stock_grade="eq=saturation=0.40:contrast=1.22:brightness=-0.05:gamma=0.92,colorbalance=bs=0.05:bm=0.03",
        music=["dark_pulse.ogg"], hook_sfx=["impact_deep", "metal_hit", "boom_low"], final_sfx="impact_deep",
        kinds=["punch", "stock", "wave", "stat", "stamp"], card_band="low",
        sfx_for={"punch": [("metal_hit", None)], "stock": [("riser", -12), ("impact_deep", None), ("whip", -12)],
                 "wave": [("sub_drop", None)], "stat": [("tick_low", -12), ("impact_deep", None)], "stamp": [("metal_hit", None)]},
        hook_anim="hard", zoom_range=(1.06, 1.22), zoom_every=(3.0, 6.0), hit_amp=(11, 15, 13), hit_punch=(0.03, 0.05, 0.04),
    ),
    "proof": dict(
        id="proof", name="Proof Cards", base_look="K1 (proof / UI cards, amber on ink)",
        css="style_proof.css", fonts=["manrope", "mono", "lora", "unbounded"],
        roles={"base": "manrope", "key": "mono", "emo": "lora", "h1": "lora", "h2": "unbounded", "h3": "mono"},
        upper=False, key_mult=0.88, emo_mult=1.22, cap_y=1500, cap_max=84, cap_w=940, gap=0.30, cap_words=5,
        hook_y=(1400, 1535, 1700), hook_size=(112, 104, 112), hook_font_role=("h1", "h2", "h3"),
        grade="eq=contrast=1.08:saturation=0.92:gamma=0.96,colorbalance=rs=0.02:bs=-0.02,unsharp=5:5:0.4:5:5:0.0",
        stock_grade="eq=saturation=0.75:contrast=1.15:brightness=-0.03",
        music=["lofi_chill.ogg"], hook_sfx=["click_hi", "boom_soft", "ping_confirm"], final_sfx="ok_c",
        kinds=["stat", "compare", "checklist", "notify", "punch", "stock"], card_band="top",
        sfx_for={"stat": [("card_in", None), ("tick_b", -12), ("coin", None), ("card_out", None)],
                 "compare": [("card_in", None), ("err_b", -10), ("ok_b", None), ("card_out", None)],
                 "checklist": [("card_in", None), ("select_b", None), ("select_b", None), ("ok_a", None), ("card_out", None)],
                 "notify": [("card_in", None), ("ping_notify", None), ("card_out", None)],
                 "punch": [("boom_soft", None)], "stock": [("whoosh_short", None), ("boom_soft", None)]},
        hook_anim="soft", zoom_range=(1.04, 1.20), zoom_every=(3.5, 6.5), hit_amp=(9, 15, 11), hit_punch=(0.03, 0.05, 0.04),
    ),
    "slab": dict(
        id="slab", name="Hazard Slab", base_look="K2 minus stickers (safety orange slabs on ink)",
        css="style_slab.css", fonts=["rubik", "rubikmono", "ptserif"],
        roles={"base": "rubik", "key": "rubikmono", "emo": "ptserif", "h1": "rubikmono", "h2": "rubikmono", "h3": "rubik"},
        upper=False, key_mult=0.8, emo_mult=1.3, cap_y=1545, cap_max=84, cap_w=940, gap=0.30, cap_words=5,
        hook_y=(1360, 1520, 1690), hook_size=(84, 100, 108), hook_font_role=("h1", "h2", "h3"),
        grade="eq=contrast=1.14:saturation=1.05:gamma=0.95,colorbalance=rs=0.04:bs=-0.04:rh=0.03",
        stock_grade="eq=saturation=0.85:contrast=1.2:brightness=-0.04",
        music=["lofi_hiphop.ogg", "dance_field.ogg"], hook_sfx=["boom_soft", "boom_low", "hit_2"], final_sfx="ding_chime",
        kinds=["punch", "stamp", "stat", "stock", "compare"], card_band="low",
        sfx_for={"punch": [("hit_1", None)], "stamp": [("stop_slam", None)], "stat": [("tick_b", -12), ("coin", None)],
                 "stock": [("whoosh_medium", -12), ("hit_3", None)], "compare": [("err_a", -10), ("ok_a", None)]},
        hook_anim="slam", zoom_range=(1.05, 1.22), zoom_every=(2.8, 5.5), hit_amp=(9, 15, 11), hit_punch=(0.03, 0.05, 0.04),
    ),
}

# sample vocabulary the planner may use for a sound-design gag (name -> what it sounds like)
SFX_VOCAB = {
    "phone_ring": "phone ringing", "alarm_short": "short alarm bell", "coin": "coin drop", "rec_scratch": "vinyl record scratch",
    "stop_slam": "hard stop slam", "bong": "single deep bong", "question": "short rising question blip", "fail_down": "descending failure tone",
    "win_up": "ascending win tone", "ding_chime": "bright chime", "ding_glass": "glass ding", "tick_a": "clock tick", "tick_low": "low clock tick",
    "pickup": "phone pick-up click", "err_a": "error buzz", "ok_c": "confirm ping", "metal_hit": "metal hit", "impact_deep": "deep impact",
    "sub_drop": "sub bass drop", "riser": "tension riser", "whip": "fast whip", "boom_low": "low boom", "click_hi": "sharp click",
    "ping_notify": "notification ping", "hit_1": "short hit", "hit_2": "hit", "hit_3": "heavy hit",
}

MUSIC_ALL = ["dark_pulse.ogg", "lofi_chill.ogg", "lofi_hiphop.ogg", "dance_field.ogg"]
MUSIC_HELP = {"dark_pulse.ogg": "dark minimal pulse (serious, tense, provocative)", "lofi_chill.ogg": "calm lo-fi (educational, reflective, soft-spoken)",
              "lofi_hiphop.ogg": "lo-fi hip-hop groove (relaxed confidence, humour, storytelling)", "dance_field.ogg": "driving upbeat pulse (urgent, energetic, results)"}
STYLE_HELP = {
    "camera": "calm (slow 1.0-1.12 pushes) | normal (1.04-1.22) | aggressive (hard 1.06-1.22 steps every 2-3 s) | locked (almost still, 1.0-1.06)",
    "hook_layout": "stack (3 stacked lines) | single (ONE giant line, 2-4 words) | split (2 lines, the second is the answer)",
    "stock_transition": "whip | zoom | flash   (how full-frame cutaways enter/leave)",
}

WILDCARDS = {
    "blackout_open": "OPENING: first ~0.5 s is pure black with only a sub-bass drop, then the picture and the hook slam in (needs at_word = first word)",
    "silence_gag": "SOUND: music and effects cut to dead silence ~0.7 s before the target word, then a deep impact lands on it",
    "negative_flash": "TRANSITION: 3-frame photographic negative of the room on the target word, with a metal hit",
    "letterbox": "FRAMING: cinematic black bars close in over the phrase first..last and open again after it",
    "echo_caption": "TEXT/SOUND: the target word is echoed three times, trailing and fading, with three ticks (a stutter)",
    "sound_gag": "SOUND-DESIGN GAG: one real-world sound (see sample list) placed exactly on the target word, e.g. phone ring on 'звонок'",
    "metaphor_stock": "VISUAL METAPHOR: a 1.3 s full-frame stock cutaway searched by `query` (e.g. 'chess pieces', 'anvil sparks', 'stopwatch')",
    "timer": "VISUAL METAPHOR: a big mono clock/counter counts value_from -> value_to (integers, seconds) over the phrase first..last (deadline, countdown, time pressure); label = what is counted",
    "split_black": "PATTERN BREAK: for ~0.9 s the room cuts to pure black and the key phrase (2-4 words, yours from the speech) stands alone in giant type while the voice continues, then the room slams back",
    "punch_cut": "FRAMING: instant jump-zoom to 1.22x on the target word for ~0.9 s, with a whip, then back",
}

BATCH_ORDER_RULE = "dark on clip numbers 1,6,11,16,...; other clips alternate proof/slab; never two equal presets in a row"


def preset_for(clip_no: int, prev: str | None) -> str:
    """Deterministic schedule: dark moody is the base for about 1 clip in 5 (1,6,11,16); between them proof/slab alternate;
    two consecutive clips never share a preset."""
    if (clip_no - 1) % 5 == 0:
        p = "dark"
    else:
        order = ["proof", "slab"]
        p = order[(clip_no - 2) % 2] if prev not in order else ("slab" if prev == "proof" else "proof")
        if p == prev:
            p = "slab" if p == "proof" else "proof"
    if p == prev:
        p = next(x for x in ("dark", "proof", "slab") if x != prev)
    return p


if __name__ == "__main__":      # tiny CLI for shell steps:  presets.py get dark grade
    import sys
    if len(sys.argv) == 4 and sys.argv[1] == "get":
        v = PRESETS[sys.argv[2]][sys.argv[3]]
        print(v if isinstance(v, str) else __import__("json").dumps(v))
    elif len(sys.argv) == 4 and sys.argv[1] == "next":
        print(preset_for(int(sys.argv[2]), sys.argv[3] if sys.argv[3] != "-" else None))
