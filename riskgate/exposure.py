"""Net market exposure, as a VERSIONED measure.

The measurement artefact this repo describes: an options book read at full delta notional with no cap at the
structure's maximum loss. A short put that has gone deep in the money carries a delta near 1, so it reads as 100 x
spot of long exposure per contract, while the most it can lose is bounded by its strikes. Summed over many such
structures, the reading more than doubled the estate's true loss bound.

    v1  sum(delta_notional x beta) / equity            a SENSITIVITY reading: unbounded, correct for a 1% move, wrong as a loss bound
    v2  sum(clip(delta_notional, max_loss) x clip(beta)) / equity   a LOSS BOUND: each defined-risk structure's exposure capped at
        what it can lose, betas clipped to a stated range, the clipped names listed

Both are printed. Which one a rule is judged on is a ruling, recorded with its date; the change from v1 to v2 went
through the same reviewer as any change to a pre-registered measure, and the v1 numbers kept their meaning.
"""
from dataclasses import dataclass

MEASURES = {
    'v1': 'raw delta notional x beta over equity: a sensitivity reading, unbounded',
    'v2': 'delta notional capped in magnitude at the structure\'s max loss, beta clipped to BETA_CLIP: a loss bound',
}
BETA_CLIP = (-2.0, 4.0)


@dataclass
class Position:
    id: str
    delta_notional: float            # signed currency exposure to the underlying (shares x spot, or options delta x 100 x spot)
    beta: float = 1.0                # to the reference index
    max_loss: float = None           # defined-risk structures: the most it can lose held to expiry; None = unbounded (stock)


def net_exposure(positions, equity, version='v2', beta_clip=BETA_CLIP):
    if version not in MEASURES:
        raise ValueError(f'unknown measure version {version!r}; known: {sorted(MEASURES)}')
    total, capped, clipped = 0.0, [], []
    for p in positions:
        dn, b = p.delta_notional, p.beta
        if version == 'v2':
            if p.max_loss is not None and abs(dn) > p.max_loss:
                capped.append({'id': p.id, 'delta_notional': dn, 'max_loss': p.max_loss})
                dn = p.max_loss if dn > 0 else -p.max_loss
            bc = min(max(b, beta_clip[0]), beta_clip[1])
            if bc != b:
                clipped.append({'id': p.id, 'beta': b, 'clipped_to': bc})
            b = bc
        total += dn * b
    return {'version': version, 'measure': MEASURES[version], 'net_exposure_pct': round(100 * total / equity, 2),
            'n_structures_capped': len(capped), 'capped': capped, 'n_beta_clipped': len(clipped), 'beta_clipped': clipped,
            'beta_clip': list(beta_clip) if version == 'v2' else None}
