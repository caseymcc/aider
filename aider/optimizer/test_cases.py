class TestCases:
    def __init__(self):
        self.test_cases = []

    def add_test_case(self, test_case):
        self.test_cases.append(test_case)

    def get_test_cases(self):
        return self.test_cases

if __name__ == "__main__":
    # Example usage
    test_cases = TestCases()
    test_cases.add_test_case("What is the capital of France?")
    test_cases.add_test_case("What is 2 + 2?")
    print(test_cases.get_test_cases())
