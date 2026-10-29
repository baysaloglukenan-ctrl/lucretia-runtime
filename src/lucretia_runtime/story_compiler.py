from __future__ import annotations

import random


WORLDS = (
    {
        "id": "workshop_hills",
        "setting": "a warm miniature workshop landscape built from rulers, boxes and wooden blocks",
        "rules": "Household objects are alive. Material properties determine every ability. No humans exist.",
    },
    {
        "id": "kitchen_harbor",
        "setting": "a bright kitchen harbor built from cups, plates, cutlery and folded towels",
        "rules": "Kitchen objects are alive. Liquids behave like seas and reflections can carry light. No humans exist.",
    },
    {
        "id": "attic_clockworks",
        "setting": "a playful attic city built from clocks, toy boxes, thread spools and paper tunnels",
        "rules": "Stored household objects are alive. Weight, friction and elasticity visibly control motion. No humans exist.",
    },
    {
        "id": "bathroom_reef",
        "setting": "a colorful bathroom reef built from soap dishes, towels, bubbles and tiled channels",
        "rules": "Bathroom objects are alive. Water, buoyancy and absorption cause visible consequences. No humans exist.",
    },
)

ATMOSPHERES = (
    "warm morning light with soft long shadows",
    "bright midday light with crisp colors",
    "golden sunset light reflected by household materials",
    "gentle moonlight with readable blue highlights",
    "colorful light after a brief rain shower",
)

METAL_HEROES = (
    ("Șurubul", "a cheerful small silver screw", "silver threaded body, round head, two large green eyes, friendly smile", "screw"),
    ("Cheița", "a curious little brass key", "polished brass key, round bow, two large blue eyes, tiny smile", "key"),
    ("Arcul", "an energetic steel spring", "shiny steel coil, two large amber eyes, elastic bouncing body", "spring"),
)

HELPERS = (
    ("Piulița", "a brave golden hexagonal nut", "golden brass hexagon, central hole, two large green eyes, expressive eyebrows", "nut"),
    ("Dopul", "a calm cork stopper", "warm cork cylinder, speckled texture, two large brown eyes, reassuring smile", "cork"),
    ("Radiera", "a clever blue rubber eraser", "small blue rubber block, rounded corners, two large violet eyes", "eraser"),
)

MAGNETS = (
    ("Magnetul Roșu", "a greedy red horseshoe magnet", "red horseshoe body, black tips, narrow yellow eyes", "magnet"),
    ("Magnetul Albastru", "an impatient blue bar magnet", "blue rectangular magnet, red ends, narrow white eyes", "bar_magnet"),
)

LIGHT_HEROES = (
    ("Avionul", "a playful little paper airplane", "white folded paper airplane, blue edge, two large green eyes", "paper_plane"),
    ("Pana", "a curious red feather", "soft red feather, curved tip, two large blue eyes", "feather"),
)

ANCHOR_HELPERS = (
    ("Mosorul", "a patient wooden thread spool", "warm wooden spool, teal thread, two large brown eyes", "spool"),
    ("Cartea", "a sturdy little blue book", "small thick blue book, golden corners, two large amber eyes", "book"),
)

WIND_THREATS = (
    ("Ventilatorul", "a boastful desk fan", "round teal desk fan, three yellow blades, narrow eyes", "fan"),
    ("Uscătorul", "an impatient red hair dryer", "small red hair dryer, dark nozzle, narrow eyes", "dryer"),
)

FLOATING_HEROES = (
    ("Bărcuța", "a brave folded paper boat", "white folded paper boat, red stripe, two large green eyes", "paper_boat"),
    ("Săpunel", "a cheerful floating soap bar", "mint oval soap bar, bubbles, two large violet eyes", "soap"),
)

ABSORBENT_HELPERS = (
    ("Buretele", "a quick yellow sponge", "yellow porous sponge, rounded corners, two large green eyes", "sponge"),
    ("Prosopul", "a calm rolled turquoise towel", "turquoise rolled towel, soft loops, two large brown eyes", "towel"),
)

WATER_THREATS = (
    ("Cana", "a careless purple pitcher", "purple ceramic pitcher, large handle, narrow eyes", "pitcher"),
    ("Robinetul", "a noisy silver faucet", "curved silver faucet, blue valve, narrow eyes", "faucet"),
)


def _magnet_story(rng: random.Random) -> dict:
    hero, helper, antagonist = rng.choice(METAL_HEROES), rng.choice(HELPERS), rng.choice(MAGNETS)
    return {
        "title": f"{hero[0]} și {antagonist[0].lower()} lacom",
        "characters": (hero, helper, antagonist),
        "plot": f"{hero[0]} pornește spre {helper[0]}. {antagonist[0]} îl capturează, dar {helper[0]} introduce o pană de lemn și întrerupe atracția.",
        "resolution_visual": "wedge",
        "captions": ("Un prieten se apropie.", "Magnetul îl capturează!", "Pana de lemn rupe atracția."),
        "scenes": (
            ("Hook", f"Immediately show {hero[0]} moving quickly toward {helper[0]}. Keep their happy greeting under one second.", f"{hero[0]} and {helper[0]} are close together.", (0, 1), 2),
            ("Conflict", f"At once, {antagonist[0]} rushes in and magnetically drags {hero[0]} away while {helper[0]} recoils in alarm.", f"{hero[0]} is captured against {antagonist[0]}; {helper[0]} remains free.", (0, 1, 2), 4),
            ("Resolution", f"Without hesitation, {helper[0]} pushes a wooden wedge between {antagonist[0]} and {hero[0]}. The magnetic pull breaks and {hero[0]} escapes.", f"The friends are safe together; the wooden wedge blocks {antagonist[0]}.", (0, 1, 2), 4),
        ),
    }


def _wind_story(rng: random.Random) -> dict:
    hero, helper, antagonist = rng.choice(LIGHT_HEROES), rng.choice(ANCHOR_HELPERS), rng.choice(WIND_THREATS)
    return {
        "title": f"{hero[0]} și furtuna din cameră",
        "characters": (hero, helper, antagonist),
        "plot": f"{antagonist[0]} suflă {hero[0]} spre un tunel periculos. {helper[0]} desfășoară un fir și îl ancorează înainte să dispară.",
        "resolution_visual": "thread",
        "captions": ("Joaca începe în aer.", "Ventilatorul pornește furtuna!", "Firul îl aduce în siguranță."),
        "scenes": (
            ("Hook", f"Immediately show {hero[0]} gliding playfully around {helper[0]}; keep the greeting under one second.", f"{hero[0]} floats close to {helper[0]}.", (0, 1), 2),
            ("Conflict", f"At once, {antagonist[0]} switches on and blasts a powerful stream of air, sending {hero[0]} toward a dark paper tunnel as {helper[0]} reacts.", f"{hero[0]} is almost blown into the tunnel; {helper[0]} stays anchored.", (0, 1, 2), 4),
            ("Resolution", f"{helper[0]} immediately unrolls a strong thread, loops it around {hero[0]} and pulls the lightweight friend safely back against the wind.", f"{hero[0]} is tethered safely beside {helper[0]}; {antagonist[0]} spins uselessly.", (0, 1, 2), 4),
        ),
    }


def _water_story(rng: random.Random) -> dict:
    hero, helper, antagonist = rng.choice(FLOATING_HEROES), rng.choice(ABSORBENT_HELPERS), rng.choice(WATER_THREATS)
    return {
        "title": f"{hero[0]} și valul grăbit",
        "characters": (hero, helper, antagonist),
        "plot": f"{antagonist[0]} varsă un val care îl poartă pe {hero[0]} spre margine. {helper[0]} absoarbe apa și creează o cale uscată de salvare.",
        "resolution_visual": "dry_path",
        "captions": ("O plimbare pe apă.", "Un val îl poartă spre margine!", "Apa este absorbită la timp."),
        "scenes": (
            ("Hook", f"Immediately show {hero[0]} floating happily beside {helper[0]}; keep the greeting under one second.", f"{hero[0]} and {helper[0]} are together beside a calm shallow puddle.", (0, 1), 2),
            ("Conflict", f"At once, {antagonist[0]} releases a rushing wave that sweeps {hero[0]} toward the edge while {helper[0]} braces against the current.", f"{hero[0]} is carried by the wave; {helper[0]} remains within reach.", (0, 1, 2), 4),
            ("Resolution", f"{helper[0]} immediately absorbs the moving water, shrinking the wave until {hero[0]} settles safely on a dry path.", f"{hero[0]} is safe beside {helper[0]}; the wave is fully absorbed and {antagonist[0]} is empty.", (0, 1, 2), 4),
        ),
    }


def compile_original_story(seed: int | None = None) -> dict:
    """Compile a causal original story from compatible world components.

    Selection is constrained by material compatibility within each conflict family.
    """

    rng = random.Random(seed)
    world = rng.choice(WORLDS)
    story = rng.choice((_magnet_story, _wind_story, _water_story))(rng)
    atmosphere = rng.choice(ATMOSPHERES)
    return {
        "title": story["title"],
        "universe_id": world["id"],
        "setting": f"{world['setting']}, {atmosphere}",
        "rules": world["rules"],
        "characters": story["characters"],
        "plot": story["plot"],
        "scenes": story["scenes"],
        "resolution_visual": story["resolution_visual"],
        "captions": story["captions"],
    }


def compile_single_shot(story: dict) -> dict:
    """Turn the internal story beats into one continuous ten-second LTX contract."""

    beats = []
    cursor = 0
    cues = []
    for title, action, end_state, _cast, duration in story["scenes"]:
        end = cursor + int(duration)
        beats.append(
            f"Seconds {cursor}-{end} ({title.lower()}): {action} "
            f"By second {end}, this must be visible: {end_state}"
        )
        cues.append({"start": cursor, "end": end, "text": story["captions"][len(cues)]})
        cursor = end
    names = ", ".join(character[0] for character in story["characters"])
    return {
        "duration_seconds": 10,
        "prompt": " ".join(
            (
                "ONE continuous vertical animated shot lasting exactly ten seconds, with no cuts, no montage and no scene reset.",
                f"Opening frame and setting: {story['setting']}.",
                f"The same canonical characters remain visible and consistent throughout: {names}.",
                *beats,
                "Start the action immediately. Preserve spatial continuity and show the complete cause, conflict and resolution before the video ends. Stable wide camera; character motion, not camera zoom.",
            )
        ),
        "negative_prompt": (
            "cuts, montage, scene transition, scene reset, time jump, slow introduction, long greeting, "
            "camera zoom, close-up, missing conflict, missing resolution, unresolved ending, frozen action"
        ),
        "required_end_state": story["scenes"][-1][2],
        "captions": cues,
    }
