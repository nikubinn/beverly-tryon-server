# prompts.py
# Detailed per-product descriptors for try-on (Gemini Image Edit).
# These are INTERNAL instructions; model + resolution + logo rules live in main.py.

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

# Helper: if some print keys vary in your catalog.json (e.g. "pink_glitter" vs "glitter"),
# keep the keys here exactly as your catalog uses them.
PRODUCT_PROMPTS = {

  # =========================
  # ALIEN DRIP T-SHIRT
  # =========================
  "alien_drip_t_shirt": {
    "garment_dna": """
GARMENT DNA:
- Oversized streetwear T-shirt, relaxed fit, dropped shoulders, wide sleeves.
- Heavyweight cotton jersey (thick), natural drape, believable folds.
- Crew neck collar: clean, symmetrical, correct thickness, realistic rib knit.
- Hem straight, sleeves slightly boxy.
""",
    "placement_dna": """
PRINT PLACEMENT DNA:
- Main graphic centered on chest.
- Scale: large statement print, but not touching collar.
- Keep symmetry left/right.
- Preserve exact print proportions from reference.
""",
    "colors": {
      "black": """
COLOR RULE:
- Deep black fabric, not washed-out grey.
- Preserve natural highlights in folds; do not over-sharpen.
"""
    },
    "prints": {
      "paint": """
PRINT DNA (PAINT):
- Two alien-eye shapes on chest, white paint style with dripping trails.
- Matte paint, slightly organic edges like real dried paint.
- Drips must match reference direction and length (no extra random drips).
- Strong contrast: clean white over black, premium look.
""",
      "glitter": """
PRINT DNA (GLITTER):
- Two alien-eye shapes on chest, metallic silver glitter with dripping trails.
- Glitter is dense and premium. Controlled sparkle (not noisy grain).
- Highlights respond to scene lighting subtly; keep shapes readable.
- Drips remain sharp and defined (no blur).
"""
    }
  },

  # =========================
  # POCKET T-SHIRT (UTILITY + BEVERLY ARCH)
  # =========================
  "pocket_t_shirt": {
    "garment_dna": """
GARMENT DNA:
- Oversized utility-style T-shirt, relaxed fit, dropped shoulders.
- Sleeve utility pockets / patches must stay visible and realistic.
- Heavy cotton jersey, structured but soft.
- Seams visible (shoulder seam, sleeve hem), realistic stitching.
""",
    "placement_dna": """
PRINT PLACEMENT DNA:
- Large arched 'BEVERLY' wordmark across chest.
- Arch curvature, letter spacing, and position must match reference.
- Print should not wrap unnaturally around torso; only mild fold-following.
""",
    "colors": {
      "black": """
COLOR RULE:
- Deep black fabric.
- Keep sleeve pocket detail readable (do not smear).
""",
      "white": """
COLOR RULE:
- Clean bright white fabric, not grey/yellow.
- Preserve natural shadows in folds.
"""
    },
    "prints": {
      "paint": """
PRINT DNA (PAINT):
- Purple paint fill inside arched 'BEVERLY' wordmark.
- Matte paint texture, slightly uneven like real paint but clean edges.
- Keep letters sharp and fully readable.
""",
      "glitter": """
PRINT DNA (DARK GLITTER):
- Dark metallic glitter fill inside arched 'BEVERLY'.
- Subtle sparkle, premium dense glitter, not grainy.
- Crisp edges and strong readability.
""",
      "pink_glitter": """
PRINT DNA (PINK GLITTER):
- Bright pink glitter fill inside arched 'BEVERLY'.
- Dense glitter with controlled sparkle; avoid neon glow blobs.
- Crisp edges, readable letters.
"""
    }
  },

  # =========================
  # PINK SWAGA T-SHIRT
  # =========================
  "pink_swaga_t_shirt": {
    "garment_dna": """
GARMENT DNA:
- Oversized pastel pink T-shirt, soft cotton, relaxed streetwear fit.
- Clean crew neck collar, smooth fabric surface.
- Keep pink tone consistent with reference (no random saturation shifts).
""",
    "placement_dna": """
GRAPHIC PLACEMENT DNA:
- Scattered organic black blob/stripe shapes across front like patches/appliqué.
- Distribution and size must match reference; do not invent new blobs.
- Shapes should look intentionally placed, not random noise.
""",
    "colors": {
      "pink": """
COLOR RULE:
- Pastel pink base fabric. Smooth, even tone.
- Preserve realistic shading in folds; do not tint skin.
"""
    },
    "prints": {
      "pink_stripes": """
PRINT DNA:
- Black blobs/stripes with a pink outline/trim (stitched edge feel).
- Outline thickness consistent, edges crisp.
- High quality appliqué look, no blur.
""",
      "white_stripes": """
PRINT DNA:
- Black blobs/stripes with a white outline/trim (stitched edge feel).
- High contrast, outline thickness consistent, edges crisp.
- No extra marks beyond reference.
"""
    }
  },

  # =========================
  # MOON WALK T-SHIRT
  # =========================
  "moon_walk_t_shirt": {
    "garment_dna": """
GARMENT DNA:
- Oversized black T-shirt, premium minimal aesthetic.
- Heavy cotton jersey, realistic folds, clean collar.
- No large front logos or text.
""",
    "placement_dna": """
TEXTURE PLACEMENT DNA:
- Lunar texture should cover the shirt fabric naturally.
- Texture follows folds smoothly; avoid loud patches or harsh edges.
""",
    "colors": {
      "default": """
COLOR RULE:
- Keep fabric black; lunar texture is subtle monochrome.
- Do not brighten into grey; preserve premium dark look.
"""
    },
    "prints": {
      "default": """
TEXTURE DNA (LUNAR):
- Subtle moon crater / lunar surface texture embedded into the fabric.
- Low contrast, premium, futuristic, minimal.
- Should look like a high-end textile print, not a sticker.
"""
    }
  }
}
