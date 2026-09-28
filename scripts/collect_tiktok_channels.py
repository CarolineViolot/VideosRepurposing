import os
import json
from datetime import datetime

from dotenv import load_dotenv

from src.tiktok_api_collection import get_access_token, fetch_user_info, load_existing_channels

if os.path.isdir("../data/"):
    os.chdir("../")

load_dotenv()

CLIENT_KEY = os.environ["TIKTOK_CLIENT_KEY"]
CLIENT_SECRET = os.environ["TIKTOK_CLIENT_SECRET"]


# ── Entry point ───────────────────────────────────────────────────────────────

def main():
    channel_type = "pp"
    if channel_type == "pp":
        channel_ids = [
            "reconqueteofficiel", "zemmour_eric", "sarah_knafo", "marion_marechal",
            "rnational_off", "jordanbardella", "mlp.officiel", "sebchenu", "julienodoul", "louis_aliot", "jphtanguy",
            "david.rachline", "edwige_diaz", "laurelavalette", "jsanchez_rn", "franckallisio", "laurentjacobelli",
            "matthieu_valet", "fabriceleggeri", "philippe_ballard",
            "eciotti",
            "lesrepublicains", "laurentwauquiez_", "brunoretailleauoff", "fxbellamy", "rachida_dati",
            "horizonsleparti", "parti_renaissance", "emmanuelmacron", "gabriel_attal", "edouardphillippe_2027",
            "gdarmanin.officiel", "olivierveran", "karl.olive", "marleneschiappa", "prisca_thevenot", "aurore_berge",
            "yaelbraunpivet",
            "ppjeunes", "partisocialiste", "fhollandeofficiel", "faure_olivier", "jerome_guedj", "borisvallaud",
            "lesecologistes", "marinetondelier", "sandrousseau", "yjadot", "marie.touss1",
            "franceinsoumisean", "jlmelenchon", "manonaubryfr", "rima.has", "mathildepanot", "manuelbompard",
            "guetteclemence", "francois_ruffin", "clementine_autain", "louisboyard", "sebastiendelogu", "alma_dufour",
            "alexis_corbiere", "deputee_obono", "eric.coquerel", "bastien.lachaud", "garrido.raquel", "thomas_portes",
            "david_guiraud", "rachel.keke.officiel", "raphael_arnault",
            "particommuniste", "fabien_roussel", "ianbrossatsenateur", "leondeffontaines",
            "npa.anticapitaliste", "lutteouvriereofficiel", "olivier.besancenot", "philippe.poutou", "nathaliearthaud",
            "dominiquedevillepin", "dupontaignannicolas", "florianphilippot", "fasselineau", "uprtvfa", "aymeric.caron"
        ]
    elif channel_type == "news":
        channel_ids = [
            "artefr", "afpfr", "bfmtv", "blast_officiel", "cdanslairofficiel.365", "c_a_vous", "cnews", "europe1",
            "france24", "france.inter", "lhumanitefr", "lexpress", "lcp_an", "lefigaro", "lemondefr", "lemediatv",
            "nouvelobs", "leparisien", "lepointfr", "lehuffpostfr", "lesechos.fr", "mariannelemag", "mediapartfr",
            "publicsenat", "rfi", "rmc_off", "rtl.officiel", "sudradio", "tf1info", "tv5monde", "va.plus",
            "franceinfo", "liberation.fr"
        ]
    output_file = f"data/tiktok/channels/{channel_type}_channels.json"
    # Authenticate
    token = get_access_token(CLIENT_KEY, CLIENT_SECRET)

    # Load previously collected channels data
    if os.path.exists(output_file):
        results = load_existing_channels(output_file)
    else:
        results = {}

    # Collect data
    for idx, username in enumerate(channel_ids, start=1):
        print(f"\n[{idx}/{len(channel_ids)}] Collecting data for: @{username}")
        user_info = fetch_user_info(username, token)
        results[username] = user_info
        results[username]["collected_at"] = datetime.date(datetime.now()).strftime(format="%y-%m-%d")
        output = {
            "total_channels": len(results),
            "channels": results,
        }
        # Save to JSON
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(output, f, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    main()