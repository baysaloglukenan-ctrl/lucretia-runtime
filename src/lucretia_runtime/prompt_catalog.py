from __future__ import annotations

from copy import deepcopy


CATALOG: dict = {
    "universes": [
        {"id": "atlas_lab", "label": "Atlas Lab", "base_prompt": "Lucretia Atlas Lab universe: strange but coherent physical experiments, controlled cinematic object behavior, tactile materials, clean visual cause and effect."},
        {"id": "creator_persona", "label": "Creator Persona", "base_prompt": "Consistent AI creator persona, cinematic social media presence, confident movement, realistic lifestyle framing."},
        {"id": "noir_signal", "label": "Noir Signal", "base_prompt": "Dark cinematic noir universe with coded signals, rain, glass reflections, neon accents, tense elegant atmosphere."},
        {"id": "mythic_machine", "label": "Mythic Machine", "base_prompt": "Mythic industrial universe where machines, symbols and ritual-like motion feel powerful, premium and cinematic."},
        {"id": "cyber_studio", "label": "Cyber Studio", "base_prompt": "Futuristic creator studio with holographic interfaces, luminous surfaces, AI production tools and controlled camera movement."},
        {"id": "urban_motion", "label": "Urban Motion", "base_prompt": "Urban kinetic short-form universe with street energy, motion blur, motorcycles, night lights and cinematic momentum."},
        {"id": "fitness_avatar", "label": "Fitness Avatar", "base_prompt": "High-performance fitness creator universe with athletic movement, gym lighting, discipline, sweat, confidence and cinematic realism."},
        {"id": "product_power", "label": "Product Power", "base_prompt": "Premium product/ad universe with strong commercial readability, hero framing, controlled reveal and clean brand-safe visual polish."},
        {"id": "surreal_comedy", "label": "Surreal Comedy", "base_prompt": "Surreal comedic universe with playful but understandable visual logic, exaggerated reactions and clean cause-and-effect gags."},
        {"id": "custom_universe", "label": "Custom Universe", "base_prompt": "Custom Lucretia universe driven by the user's scene and prompt direction."},
    ],
    "scenes": [
        {"id": "lab_object_awake", "universe_id": "atlas_lab", "label": "Object wakes", "base_prompt": "A single object slowly activates on a laboratory table, subtle vibration, clean close-up, visible cause and effect."},
        {"id": "lab_magnetic_pull", "universe_id": "atlas_lab", "label": "Magnetic pull", "base_prompt": "Small metal elements move toward a central object in a controlled magnetic pull, readable motion, no random deformation."},
        {"id": "lab_chain_reaction", "universe_id": "atlas_lab", "label": "Chain reaction", "base_prompt": "A short tactile chain reaction across a tabletop, one clear action triggering the next, satisfying motion."},
        {"id": "lab_material_transform", "universe_id": "atlas_lab", "label": "Material transform", "base_prompt": "A material changes texture or shape in a visually coherent way, macro detail, clear physical transformation."},
        {"id": "creator_intro", "universe_id": "creator_persona", "label": "Creator intro", "base_prompt": "AI creator persona enters frame with confident posture, cinematic social reel intro, clean realistic environment."},
        {"id": "creator_gym", "universe_id": "creator_persona", "label": "Gym presence", "base_prompt": "Consistent creator persona in a modern gym, controlled athletic motion, confident but platform-safe framing."},
        {"id": "creator_lifestyle", "universe_id": "creator_persona", "label": "Lifestyle cut", "base_prompt": "Lifestyle creator shot with natural movement, premium casual environment, warm realistic camera language."},
        {"id": "creator_closeup", "universe_id": "creator_persona", "label": "Close-up identity", "base_prompt": "Clean close-up portrait movement with consistent face identity, subtle expression shift, no text overlay."},
        {"id": "noir_reveal", "universe_id": "noir_signal", "label": "Noir reveal", "base_prompt": "A figure or object is revealed through rain-streaked glass and neon reflections, slow tension build."},
        {"id": "noir_signal_device", "universe_id": "noir_signal", "label": "Signal device", "base_prompt": "A small mysterious device pulses with coded light on a dark table, cinematic noir atmosphere."},
        {"id": "noir_chase_fragment", "universe_id": "noir_signal", "label": "Chase fragment", "base_prompt": "Brief kinetic noir chase fragment through wet city lights, tight camera, readable motion."},
        {"id": "mythic_engine_start", "universe_id": "mythic_machine", "label": "Engine start", "base_prompt": "A powerful machine awakens like a ritual object, glowing accents, smoke, controlled dramatic movement."},
        {"id": "mythic_symbol_burn", "universe_id": "mythic_machine", "label": "Symbol ignition", "base_prompt": "A symbol ignites across metal or glass, premium cinematic macro shot, powerful transformation."},
        {"id": "mythic_assembly", "universe_id": "mythic_machine", "label": "Assembly ritual", "base_prompt": "Mechanical pieces assemble with ritual precision, cinematic lighting, satisfying locked-in motion."},
        {"id": "cyber_prompt_room", "universe_id": "cyber_studio", "label": "Prompt room", "base_prompt": "A futuristic creator operates floating AI prompt panels in a luminous studio, smooth camera push."},
        {"id": "cyber_generation_wall", "universe_id": "cyber_studio", "label": "Generation wall", "base_prompt": "A wall of generated visual fragments activates around the creator, coherent production interface, no readable text."},
        {"id": "cyber_asset_forge", "universe_id": "cyber_studio", "label": "Asset forge", "base_prompt": "Digital assets form from light particles into a clean visual object, production-grade sci-fi studio feel."},
        {"id": "urban_bike_detail", "universe_id": "urban_motion", "label": "Bike detail", "base_prompt": "Close-up motorcycle detail under night lights, reflections, slow reveal, cinematic speed energy."},
        {"id": "urban_night_roll", "universe_id": "urban_motion", "label": "Night roll", "base_prompt": "Urban night rolling shot with motion blur, street lights and powerful forward movement."},
        {"id": "urban_arrival", "universe_id": "urban_motion", "label": "Arrival shot", "base_prompt": "A dramatic arrival moment in an urban location, headlights, smoke or mist, confident cinematic framing."},
        {"id": "fitness_power_set", "universe_id": "fitness_avatar", "label": "Power set", "base_prompt": "Athletic power movement in gym lighting, focused expression, clean performance framing."},
        {"id": "fitness_mirror_walk", "universe_id": "fitness_avatar", "label": "Mirror walk", "base_prompt": "Confident gym mirror walk with realistic body movement, high-retention social reel camera."},
        {"id": "fitness_cut_sequence", "universe_id": "fitness_avatar", "label": "Cut sequence", "base_prompt": "Fast but readable fitness sequence with 2-3 clean motion beats, disciplined cinematic rhythm."},
        {"id": "product_hero", "universe_id": "product_power", "label": "Hero product", "base_prompt": "Premium hero shot of a product on a clean surface, strong silhouette, slow push-in, commercial clarity."},
        {"id": "product_macro", "universe_id": "product_power", "label": "Macro detail", "base_prompt": "Macro detail of product material, highlights, texture and premium finish, smooth controlled motion."},
        {"id": "product_reveal", "universe_id": "product_power", "label": "Reveal sequence", "base_prompt": "A product is revealed from shadow or motion, satisfying reveal, clean brand-safe composition."},
        {"id": "surreal_object_gag", "universe_id": "surreal_comedy", "label": "Object gag", "base_prompt": "A simple object performs one absurd but readable action, comedic timing, no chaotic deformation."},
        {"id": "surreal_reaction", "universe_id": "surreal_comedy", "label": "Reaction beat", "base_prompt": "A character or object reacts in an exaggerated but clear way to a single visual event."},
        {"id": "surreal_loop", "universe_id": "surreal_comedy", "label": "Loop gag", "base_prompt": "A looping surreal action that can work as a short-form hook, clear beginning and repeatable ending."},
        {"id": "custom_scene", "universe_id": "custom_universe", "label": "Custom scene", "base_prompt": "User-defined scene. Follow the custom prompt as the primary direction."},
    ],
    "presets": [
        {"id": "hook_fast", "label": "Hook fast", "base_prompt": "Strong opening motion in the first second, high-retention visual hook, immediate subject clarity."},
        {"id": "cinematic_slow", "label": "Cinematic slow", "base_prompt": "Slow premium camera movement, controlled lighting, elegant pacing, atmospheric polish."},
        {"id": "macro_premium", "label": "Macro premium", "base_prompt": "Macro lens feel, shallow depth of field, premium highlights, tactile detail."},
        {"id": "dark_luxury", "label": "Dark luxury", "base_prompt": "Dark premium lighting, glossy reflections, deep contrast, powerful cinematic tone."},
        {"id": "viral_clean", "label": "Viral clean", "base_prompt": "Clean TikTok/Reels visual grammar, readable motion, strong center composition, no clutter."},
        {"id": "raw_realistic", "label": "Raw realistic", "base_prompt": "Realistic handheld energy, believable motion, natural lighting, documentary-like presence."},
        {"id": "neon_kinetic", "label": "Neon kinetic", "base_prompt": "Neon accents, kinetic camera, urban energy, controlled speed and motion blur."},
        {"id": "soft_identity", "label": "Soft identity", "base_prompt": "Identity-focused framing, flattering soft light, consistent subject presence, subtle expression."},
        {"id": "absurd_controlled", "label": "Absurd controlled", "base_prompt": "Absurd concept, but visually logical and controlled, no random mutations, one clear gag."},
        {"id": "trailer_beat", "label": "Trailer beat", "base_prompt": "Short trailer-like beat, dramatic reveal, high contrast, premium suspense, strong final frame."},
    ],
}


def get_catalog() -> dict:
    return deepcopy(CATALOG)


def _find(items: list[dict], item_id: str) -> dict | None:
    return next((item for item in items if item.get("id") == item_id), None)


def compose_prompt(universe_id: str, scene_id: str, preset_id: str, custom_prompt: str = "") -> str:
    universe = _find(CATALOG["universes"], universe_id) or CATALOG["universes"][0]
    scene = _find(CATALOG["scenes"], scene_id) or CATALOG["scenes"][0]
    preset = _find(CATALOG["presets"], preset_id) or CATALOG["presets"][0]
    parts = [universe["base_prompt"], scene["base_prompt"], preset["base_prompt"]]
    if custom_prompt.strip():
        parts.append(f"Custom direction: {custom_prompt.strip()}.")
    parts.append("Vertical 720:1280 short-form video. Smooth camera motion. Strong first-second hook. No captions or text overlay. Keep visual logic coherent.")
    return " ".join(parts).strip()
