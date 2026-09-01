"""skillforge — a WikiSkill-style skill-evolution loop for this repo.

An independent reimplementation of the method in:

    WikiSkill: Compiling Agent Experience into Persistent Knowledge for
    Skill Evolution. Liyan Tang, Cyrus Rashtchian, Chun-Sung Ferng,
    Andrew Tomkins, Da-Cheng Juan, Tu Vu. Google Research / Virginia Tech.
    arXiv:2608.27454v1 [cs.AI], 27 Aug 2026. CC BY 4.0.

All credit for the method, the three-layer architecture, Algorithm 1, and the
agent designs belongs to the paper's authors. This package is a study
reimplementation; it is not affiliated with Google.

This is a SEPARATE project inside the SillyTavernPresets repo (like
voicekit-starter/). None of the bot rules apply to it: no BOT_VERSION, no
CHANGELOG gate, no fleet deploy. It never reads or writes the .claude/ memory
layer.
"""

__version__ = "0.1.0"
