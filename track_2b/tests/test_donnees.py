"""Contrôles des données OFSP 2027 : primes enfants et modèles réservés à certaines communes.
Lancer : python tests/test_donnees.py"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import comparateur as k


def test_enfant_prime_sans_rabais_famille():
    # Un enfant seul paie la prime K1 ; les rabais K3/K4/K5 (2e ou 3e enfant) ne doivent pas apparaître
    offres = k._filtrer("NE", 0, 8, 0, True)
    assert set(offres["Altersuntergruppe"]) == {"K1"}
    assert k.toutes_les_offres("NE", 0, 8, 0, True).iloc[0]["Prime/mois"] == 128.40


def test_adultes_et_jeunes_sous_groupe_de_base():
    assert set(k._filtrer("VD", 1, 30, 2500, False)["Altersuntergruppe"]) == {"E1"}
    assert set(k._filtrer("VD", 1, 22, 2500, False)["Altersuntergruppe"]) == {"J1"}


def test_modele_reserve_a_certaines_communes():
    regs = k.regions.drop_duplicates("no_ofs")
    for (assureur, canton, region, tarif), communes in k.CIRCONSCRIPTIONS.items():
        r = int(region[-1])
        dans_region = regs[(regs.canton == canton) & (regs.region == r)]
        dedans = dans_region[dans_region.no_ofs.isin(communes)].no_ofs
        dehors = dans_region[~dans_region.no_ofs.isin(communes)].no_ofs

        def propose(no_ofs):
            f = k._filtrer(canton, r, 30, 300, False, ["PRAXIS"], no_ofs=no_ofs)
            return bool(((f.Versicherer == assureur) & (f.Tarif == tarif)).any())

        assert propose(int(dedans.iloc[0])), (assureur, canton, region, tarif)
        if len(dehors):
            assert not propose(int(dehors.iloc[0])), (assureur, canton, region, tarif)
        assert not propose(None), (assureur, canton, region, tarif)


if __name__ == "__main__":
    tests = [f for nom, f in dict(globals()).items() if nom.startswith("test_")]
    for t in tests:
        t()
    print(f"{len(tests)} tests réussis")
