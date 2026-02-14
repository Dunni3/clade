"""Scientist name pool for brother naming suggestions."""

from __future__ import annotations

import random

SCIENTISTS: list[dict[str, str]] = [
    {"name": "curie", "full": "Marie Curie", "bio": "Pioneered radioactivity research"},
    {"name": "darwin", "full": "Charles Darwin", "bio": "Theory of evolution by natural selection"},
    {"name": "feynman", "full": "Richard Feynman", "bio": "Quantum electrodynamics pioneer"},
    {"name": "lovelace", "full": "Ada Lovelace", "bio": "First computer programmer"},
    {"name": "turing", "full": "Alan Turing", "bio": "Father of theoretical computer science"},
    {"name": "rosalind", "full": "Rosalind Franklin", "bio": "Key to discovering DNA structure"},
    {"name": "tesla", "full": "Nikola Tesla", "bio": "Alternating current electrical systems"},
    {"name": "hopper", "full": "Grace Hopper", "bio": "Invented the first compiler"},
    {"name": "euler", "full": "Leonhard Euler", "bio": "Prolific mathematician"},
    {"name": "gauss", "full": "Carl Friedrich Gauss", "bio": "Prince of mathematicians"},
    {"name": "planck", "full": "Max Planck", "bio": "Originated quantum theory"},
    {"name": "noether", "full": "Emmy Noether", "bio": "Abstract algebra and symmetry in physics"},
    {"name": "ramanujan", "full": "Srinivasa Ramanujan", "bio": "Self-taught mathematical genius"},
    {"name": "mendel", "full": "Gregor Mendel", "bio": "Father of modern genetics"},
    {"name": "pasteur", "full": "Louis Pasteur", "bio": "Germ theory and pasteurization"},
    {"name": "faraday", "full": "Michael Faraday", "bio": "Electromagnetic induction"},
    {"name": "kepler", "full": "Johannes Kepler", "bio": "Laws of planetary motion"},
    {"name": "lise", "full": "Lise Meitner", "bio": "Nuclear fission discovery"},
    {"name": "bohr", "full": "Niels Bohr", "bio": "Atomic structure model"},
    {"name": "hypatia", "full": "Hypatia of Alexandria", "bio": "Ancient mathematician and philosopher"},
    {"name": "archimedes", "full": "Archimedes", "bio": "Eureka — buoyancy and levers"},
    {"name": "leibniz", "full": "Gottfried Leibniz", "bio": "Co-invented calculus"},
    {"name": "fermi", "full": "Enrico Fermi", "bio": "Nuclear reactor pioneer"},
    {"name": "pavlov", "full": "Ivan Pavlov", "bio": "Classical conditioning research"},
    {"name": "hubble", "full": "Edwin Hubble", "bio": "Expanding universe discovery"},
]


def suggest_name(used: list[str] | None = None) -> dict[str, str]:
    """Return a random unused scientist entry.

    Args:
        used: List of names already in use.

    Returns:
        A dict with 'name', 'full', and 'bio' keys.
    """
    used = used or []
    available = [s for s in SCIENTISTS if s["name"] not in used]
    if not available:
        # All names used — fall back to full pool
        available = SCIENTISTS
    return random.choice(available)


def format_suggestion(entry: dict[str, str]) -> str:
    """Format a scientist entry for display.

    Args:
        entry: A scientist dict from SCIENTISTS.

    Returns:
        A formatted string like 'curie (Marie Curie — Pioneered radioactivity research)'
    """
    return f"{entry['name']} ({entry['full']} — {entry['bio']})"
