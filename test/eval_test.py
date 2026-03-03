import logfire
from pydantic_evals import Case, Dataset
from pydantic_evals.evaluators import ConfusionMatrixEvaluator

# Configure Logfire
logfire.configure(
    send_to_logfire='if-token-present',  
)

def my_classifier(text: str) -> str:
    text = text.lower()
    if 'cat' in text or 'meow' in text:
        return 'cat'
    elif 'dog' in text or 'bark' in text:
        return 'dog'
    return 'unknown'


dataset = Dataset(
    cases=[
        Case(name='cat', inputs='The cat goes meow', expected_output='cat'),
        Case(name='dog', inputs='The dog barks', expected_output='dog'),
    ],
    report_evaluators=[
        ConfusionMatrixEvaluator(
            predicted_from='output',
            expected_from='expected_output',
            title='Animal Classification',
        ),
    ],
)

report = dataset.evaluate_sync(my_classifier)
# report.analyses contains the ConfusionMatrix result
print(report.analyses)