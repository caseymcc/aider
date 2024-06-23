import json

class Evaluator:
    def __init__(self, results):
        self.results = results

    def evaluate(self):
        # For simplicity, we will just return the results as is
        return self.results

if __name__ == "__main__":
    # Example usage
    results = [
        {
            "prompt": "Answer the following questions:",
            "results": [
                "The capital of France is Paris.",
                "2 + 2 is 4."
            ]
        }
    ]
    evaluator = Evaluator(results)
    evaluation = evaluator.evaluate()
    print(json.dumps(evaluation, indent=2))
