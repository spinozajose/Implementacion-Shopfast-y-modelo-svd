"""Genera un dataset sintético y reproducible para el prototipo ShopFast (EP3).

Uso:  python dataset/generate_dataset.py --out data
Salida: data/products.csv, data/users.csv, data/interactions.csv
"""
import argparse
from pathlib import Path

import numpy as np
import pandas as pd

SEED = 42
N_USERS, N_PRODUCTS, N_INTERACTIONS = 5000, 500, 150_000
RATING = {"view": 1, "click": 2, "cart": 4, "purchase": 5}
CATEGORIES = ["Smartphones", "Laptops", "Audio", "Gaming", "Accesorios",
              "Smart Home", "Wearables", "Cámaras"]
PRICE_RANGE = {"Smartphones": (150, 1200), "Laptops": (350, 2200), "Audio": (15, 400),
               "Gaming": (20, 600), "Accesorios": (5, 80), "Smart Home": (15, 250),
               "Wearables": (30, 450), "Cámaras": (60, 1500)}


def main(out: Path) -> None:
    rng = np.random.default_rng(SEED)
    out.mkdir(parents=True, exist_ok=True)

    # --- Productos ---
    cats = rng.choice(CATEGORIES, N_PRODUCTS)
    prices = [round(float(rng.uniform(*PRICE_RANGE[c])), 2) for c in cats]
    pop = rng.pareto(1.5, N_PRODUCTS) + 1          # popularidad con cola larga
    products = pd.DataFrame({
        "product_id": [f"P{i:04d}" for i in range(N_PRODUCTS)],
        "name": [f"{c} modelo {i:03d}" for i, c in enumerate(cats)],
        "category": cats, "price": prices})

    # --- Usuarios: cada uno prefiere 2 categorías (seudonimizados: sin datos personales) ---
    users = pd.DataFrame({"user_id": [f"U{i:05d}" for i in range(N_USERS)]})
    fav = np.array([rng.choice(len(CATEGORIES), 2, replace=False) for _ in range(N_USERS)])
    cat_idx = np.array([CATEGORIES.index(c) for c in cats])

    # --- Interacciones: pares únicos usuario-producto, sesgados por afinidad ---
    per_user = rng.multinomial(N_INTERACTIONS, np.ones(N_USERS) / N_USERS)
    per_user = np.clip(per_user, 5, N_PRODUCTS // 2)
    rows = []
    t0 = pd.Timestamp("2026-01-01")
    for u in range(N_USERS):
        match = np.isin(cat_idx, fav[u])
        w = pop * np.where(match, 6.0, 1.0)
        w = w / w.sum()
        items = rng.choice(N_PRODUCTS, per_user[u], replace=False, p=w)
        for p in items:
            aff = 0.75 if match[p] else 0.15       # prob. de interacción "fuerte"
            if rng.random() < aff:
                itype = rng.choice(["click", "cart", "purchase"], p=[0.35, 0.30, 0.35])
            else:
                itype = rng.choice(["view", "click"], p=[0.8, 0.2])
            ts = t0 + pd.Timedelta(minutes=int(rng.integers(0, 60 * 24 * 300)))
            rows.append((users.user_id[u], products.product_id[p], itype, RATING[itype],
                         ts.isoformat(), cats[p], prices[p]))

    inter = pd.DataFrame(rows, columns=["user_id", "product_id", "interaction_type",
                                        "rating", "timestamp", "category", "price"])
    inter = inter.drop_duplicates(["user_id", "product_id"]).reset_index(drop=True)

    products.to_csv(out / "products.csv", index=False)
    users.to_csv(out / "users.csv", index=False)
    inter.to_csv(out / "interactions.csv", index=False)
    print(f"usuarios={len(users)} productos={len(products)} interacciones={len(inter)}")
    print({k: int(v) for k, v in inter.interaction_type.value_counts().items()})


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="data", type=Path)
    main(ap.parse_args().out)
