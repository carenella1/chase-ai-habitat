from habitat.runtime.kernel import HabitatKernel


def main():
    kernel = HabitatKernel()
    kernel.run_forever(interval_seconds=120)


if __name__ == "__main__":
    main()