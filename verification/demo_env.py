"""Create local-only synthetic demo credentials in the ignored work directory."""
from pathlib import Path
from secrets import token_hex


def main():
    destination = Path(__file__).resolve().parents[1] / "work" / "ghost-demo.env"
    destination.parent.mkdir(exist_ok=True)
    values = {key: "Gh9!" + token_hex(16) for key in (
        "GHOST_PG_ADMIN_PASSWORD", "GHOST_SEARCH_ADMIN_PASSWORD", "GHOST_PG_READ_PASSWORD",
        "GHOST_SEARCH_PASSWORD")}
    values["GHOST_PG_DSN"] = (
        "host=127.0.0.1 port=45432 dbname=ghost_demo user=ghost_auditor password="
        + values["GHOST_PG_READ_PASSWORD"])
    values["GHOST_DEMO_CERT"] = "1"
    try:
        with destination.open("x", encoding="utf-8") as stream:
            stream.write("".join(f"{key}={value}\n" for key, value in values.items()))
    except FileExistsError:
        print("Existing demo credentials were reused.")
    else:
        print("Created work/ghost-demo.env. Keep it local.")


if __name__ == "__main__":
    main()
