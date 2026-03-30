from habitat.orchestration.steward import Steward
from habitat.storage.sqlite_store import initialize_db


def main():

    print("Starting Chase AI Habitat")

    initialize_db()

    steward = Steward()
    steward.boot()

    print("Habitat is running")


if __name__ == "__main__":
    main()