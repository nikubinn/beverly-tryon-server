# prompts.py
# Internal prompt descriptors for try-on (Gemini Image Edit)
# Keys MUST match catalog.json exactly.

GLOBAL_CONSTRAINTS = """
HARD CONSTRAINTS (must follow):
- Edit ONLY the T-shirt. Do not change face, hair, skin texture, body proportions, pose, hands, background, lighting direction, or other clothing items.
- Keep realism: correct perspective, shadows, fabric folds, collar, seams.
- No extra text, no invented logos, no new graphics.
- Do not add or remove accessories.
- Do not alter pants, shorts, shoes, or other garments.
- Do not add skin marks or new facial details.
"""

GLOBAL_QUALITY = """
QUALITY TARGET:
- Photorealistic fashion photo.
- Clean premium garment look.
- Crisp print edges, no blur, no melting, no double printing.
- Print follows fabric folds subtly (only mild warping from real drape).
- No floating prints, no sticker look.
"""

GLOBAL_LOGO_RULES = """
LOGO PLACEMENT RULES (must follow):
- Use the provided logo image ONLY as a real physical object in the environment.
- Allowed forms: small sticker on a wall or door, small sign plate, small poster, label on a surface object, or small sticker on a mirror frame.
- The logo must be physically attached to a surface with correct perspective and contact shadow.
- The logo must NOT float and must NOT be an overlay.

WHERE TO PLACE (choose ONE natural option):
- Plain wall area
- Door or cabinet surface
- Mirror frame corner
- Small sign or plate on a wall or shelf
- Small poster or paper taped to a wall

STYLE:
- Keep it small and secondary, never dominating the frame.
- Subtle violet glow or sheen with gentle light bleed onto the surface.
- If far in background: slightly out of focus.
- If closer: sharp but still subtle.
- No harsh bloom, no neon blobs, no HDR halos.

STRICT:
- DO NOT place the logo on the T-shirt or any clothing.
- DO NOT add any other text, slogans, extra logos, watermarks, or signatures.
- DO NOT place the logo in the sky, empty air, or as a floating graphic.
- DO NOT modify the environment to make space for the logo.
"""

PRODUCT_PROMPTS = {

    # =========================
    # ALIEN DRIP T-SHIRT
    # =========================
    "alien_drip_t_shirt": {
        "garment_dna": """
GARMENT DNA:
- Oversized streetwear T-shirt.
- Relaxed fit, dropped shoulders, wide sleeves.
- Heavyweight cotton jersey, thick and premium.
- Natural drape with believable folds.
- Crew neck collar, clean and symmetrical.
""",
        "placement_dna": """
PRINT PLACEMENT DNA:
- Main alien-eyes graphic centered on the chest.
- Large statement size, not touching the collar.
- Perfect left/right symmetry.
- Exact proportions from the reference image.
""",
        "colors": {
            "black": "COLOR RULE: deep black fabric, preserve natural highlights in folds.",
            "white": "COLOR RULE: clean bright white fabric, no yellow tint.",
            "pink":  "COLOR RULE: soft pastel pink, even tone, do not tint skin."
        },
        "prints": {
            "paint": """
PRINT DNA (PAINT):
- Two alien-eye shapes with dripping trails.
- Matte paint texture, organic but controlled edges.
- Drips match reference direction and length.
- High contrast, premium finish.
""",
            "glitter": """
PRINT DNA (GLITTER):
- Two alien-eye shapes with dripping trails.
- Dense metallic glitter texture.
- Controlled sparkle, no grainy noise.
- Drips remain sharp and readable.
"""
        }
    },

    # =========================
    # POCKET T-SHIRT
    # =========================
    "pocket_t_shirt": {
        "garment_dna": """
GARMENT DNA:
- Oversized utility-style T-shirt.
- Relaxed fit with dropped shoulders.
- Sleeve utility pockets must remain visible.
- Heavy cotton jersey, structured but soft.
- Visible seams and realistic stitching.
""",
        "placement_dna": """
PRINT PLACEMENT DNA:
- Large arched 'BEVERLY' wordmark across chest.
- Arch curvature and spacing must match reference.
- Print follows fabric folds subtly.
""",
        "colors": {
            "black": "COLOR RULE: deep black fabric, keep pocket details readable.",
            "white": "COLOR RULE: clean bright white fabric, preserve shadows."
        },
        "prints": {
            "paint": """
PRINT DNA (PAINT):
- Purple paint fill inside arched 'BEVERLY'.
- Matte paint texture, slightly uneven but clean.
- Letters fully readable.
""",
            "glitter": """
PRINT DNA (DARK GLITTER):
- Dark metallic glitter fill.
- Subtle premium sparkle.
- Crisp edges, high readability.
""",
            "pink_glitter": """
PRINT DNA (PINK GLITTER):
- Bright pink glitter fill.
- Dense controlled sparkle.
- Avoid neon glow or bloom.
"""
        }
    },

    # =========================
    # PINK SWAGA T-SHIRT
    # =========================
    "pink_swaga_t_shirt": {
        "garment_dna": """
GARMENT DNA:
- Oversized T-shirt.
- Relaxed streetwear fit.
- Smooth cotton surface, premium finish.
""",
        "placement_dna": """
GRAPHIC PLACEMENT DNA:
- Organic black blob/stripe shapes across the shirt.
- Distribution and scale match reference exactly.
- No new shapes added.
""",
        "colors": {
            "pink":  "COLOR RULE: pastel pink base, even tone, do not tint skin.",
            "white": "COLOR RULE: clean white base, preserve natural shadows."
        },
        "prints": {
            "stripes": """
PRINT DNA (STRIPES/BLOBS):
- Organic black shapes with clean outline.
- Consistent thickness, crisp edges.
- High-quality appliqué look.
"""
        }
    },

    # =========================
    # MOON WALK T-SHIRT
    # =========================
    "moon_walk_t_shirt": {
        "garment_dna": """
GARMENT DNA:
- Oversized black T-shirt.
- Premium minimal aesthetic.
- Heavy cotton jersey, realistic folds.
- Clean collar, no large logos.
""",
        "placement_dna": """
TEXTURE PLACEMENT DNA:
- Lunar texture integrated into the fabric.
- Texture follows folds naturally.
- No harsh edges or loud patches.
""",
        "colors": {
            "default": "COLOR RULE: keep fabric deep black, lunar texture subtle and monochrome."
        },
        "prints": {
            "default": """
TEXTURE DNA (LUNAR):
- Subtle moon crater texture.
- Low contrast, futuristic, minimal.
- Looks like textile, not a sticker.
"""
        }
    }
}
