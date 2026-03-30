from habitat.agents.insight_agent import InsightAgent


def main():

    agent = InsightAgent()

    result = agent.run()

    print("\nHabitat Insight:\n")
    print(result)


if __name__ == "__main__":
    main()