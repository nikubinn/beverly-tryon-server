# prompts.py
# Internal prompt descriptors for try-on (Gemini Image Edit)
# Keys MUST match catalog.json exactly.

GLOBAL_CONSTRAINTS = """
HARD CONSTRAINTS (must follow):
- Edit ONLY the T-shirt. Do not change face, hair, skin texture, body proportions, pose, hands, background, lighting direction, or other clothing items.
- Keep realism: correct perspective, shadows, fabric folds, collar, seams.
- No extra text, no invented logos, no new graphics.
- Do not add or remove accessories. Do not alter pants/shorts/shoes.
- Do not add skin marks or new facial details.
"""

GLOBAL_QUALITY = """
QUALITY TARGET:
- Photorealistic fashion photo, clean premium garment.
- Crisp print edges, no blur, no melting, no double printing.
- Print follows fabric folds subtly (only mild warping from real drape), never floating.
"""

GLOBAL_LOGO_RULES = """
LOGO PLACEMENT RULES:
- Use the provided logo ONLY as a physical object in the environment (sign, sticker, plate, poster, wall mark).
- Logo must feel naturally integrated into the scene.
- Keep it small and secondary; never dominate the frame.
- Add a subtle violet glow/sheen that softly spills onto the surface (gentle light bleed).
- Slightly out of focus if far in the background; if closer, keep it sharp but still subtle.
- Avoid harsh bloom, oversaturated neon blobs, or unrealistic HDR halos.

STRICT LOGO CONSTRAINTS:
- DO NOT place the logo on the T-shirt or any clothing.
- DO NOT add any other text, slogans, extra logos, watermarks, or signatures.
- DO NOT put the logo in the sky, in empty air, or as a floating overlay.
"""

PRODUCT_PROMPTS = {
    ...
}
