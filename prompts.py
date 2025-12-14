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
- Main alien-eyes graphic centered on the chest.
- Scale: large statement print, not touching the collar.
- Keep symmetry left/right.
- Preserve exact print proportions from reference.
""",
    "colors": {
      "black": "COLOR RULE: deep black fabric, keep natural highlights in folds.",
      "white": "COLOR RULE: clean bright white fabric, keep natural shadows in folds, no yellow tint.",
      "pink":  "COLOR RULE: pastel pink fabric tone, even and premium, do not tint skin."
    },
    "prints": {
      "paint": """
PRINT DNA (PAINT):
- Two alien-eye shapes on chest with dripping trails.
- Matte paint look, slightly organic edges like real dried paint.
- Drips must match reference direction and length (no extra random drips).
- Keep high contrast and clean premium finish.
""",
      "glitter": """
PRINT DNA (GLITTER):
- Two alien-eye shapes on chest with dripping trails.
- Metallic glitter texture, dense and premium. Controlled sparkle (not noisy grain).
- Highlights respond to lighting subtly; keep shapes readable.
- Drips remain sharp and defined (no blur).
"""
    }
  },

  # =========================
  # POCKET T-SHIRT
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
      "black": "COLOR RULE: deep black fabric; keep sleeve pocket detail readable.",
      "white": "COLOR RULE: clean bright white fabric; preserve natural shadows."
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
  # catalog has print key: "stripes" and color defines which variant image is used
  # =========================
  "pink_swaga_t_shirt": {
    "garment_dna": """
GARMENT DNA:
- Oversized T-shirt, relaxed streetwear fit.
- Clean crew neck collar, smooth cotton surface, premium finish.
""",
    "placement_dna": """
GRAPHIC PLACEMENT DNA:
- Scattered organic black blob/stripe shapes across the shirt like appliqué patches.
- Distribution and size must match the reference exactly; do not invent new blobs.
- Shapes must look intentionally placed, not random noise.
""",
    "colors": {
      "pink":  "COLOR RULE: pastel pink base fabric, even tone, do not tint skin.",
      "white": "COLOR RULE: clean white base fabric, preserve natural shadows."
    },
    "prints": {
      "stripes": """
PRINT DNA (STRIPES/BLOBS):
- Organic black blobs/stripes with an outline/trim that matches the reference image for this selected color.
- Outline must be clean, consistent thickness, crisp edges.
- High-quality patch/appliqué look, no blur.
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
- No large front logos or big text.
""",
    "placement_dna": """
TEXTURE PLACEMENT DNA:
- Lunar texture should cover the shirt fabric naturally.
- Texture follows folds smoothly; avoid loud patches or harsh edges.
""",
    "colors": {
      "default": "COLOR RULE: keep fabric black; lunar texture is subtle monochrome; do not brighten into grey."
    },
    "prints": {
      "default": """
TEXTURE DNA (LUNAR):
- Subtle moon crater / lunar surface texture embedded into the fabric.
- Low contrast, premium, futuristic, minimal.
- Looks like a high-end textile print, not a sticker.
"""
    }
  }
}
