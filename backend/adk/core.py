from typing import List, Callable, Any, Dict, Optional
import time

class Context:
    def __init__(self, logger: Callable = print):
        self.data: Dict[str, Any] = {}
        self.history: List[Dict[str, Any]] = []
        self.logger = logger

    def set(self, key: str, value: Any):
        self.data[key] = value

    def get(self, key: str) -> Any:
        return self.data.get(key)

    def log(self, step_name: str, input: Any, output: Any):
        self.history.append({
            "step": step_name,
            "timestamp": time.time(),
            "input": str(input),
            "output": str(output)
        })

class Tool:
    def __init__(self, name: str, func: Callable, description: str):
        self.name = name
        self.func = func
        self.description = description

    def execute(self, *args, **kwargs):
        return self.func(*args, **kwargs)

class Step:
    def __init__(self, name: str, action: Callable[[Context], Any]):
        self.name = name
        self.action = action

    def run(self, context: Context, logger: Callable = print):
        logger(f"--- Running Step: {self.name} ---")
        result = self.action(context)
        context.log(self.name, context.get("last_input"), result)
        return result

class LoopStep(Step):
    def __init__(self, name: str, action: Callable[[Context], Any], condition: Callable[[Context, Any], bool], max_iterations: int = 3):
        super().__init__(name, action)
        self.condition = condition
        self.max_iterations = max_iterations

    def run(self, context: Context, logger: Callable = print):
        logger(f"--- Running Loop Step: {self.name} ---")
        iteration = 0
        result = None
        while iteration < self.max_iterations:
            iteration += 1
            logger(f"  > Iteration {iteration}/{self.max_iterations}")
            result = self.action(context)
            if self.condition(context, result):
                logger("  > Loop condition met.")
                break
            logger("  > Loop condition not met, retrying...")
        
        context.log(self.name, f"Loop finished after {iteration} iters", result)
        return result

class SequentialWorkflow:
    def __init__(self, name: str):
        self.name = name
        self.steps: List[Step] = []

    def add_step(self, step: Step):
        self.steps.append(step)

    def execute(self, initial_input: Any, logger: Callable = print) -> Context:
        context = Context(logger=logger)
        context.set("initial_input", initial_input)
        context.set("last_input", initial_input)
        
        for step in self.steps:
            try:
                result = step.run(context, logger=logger)
                context.set("last_input", result) # Chain output to next input
            except Exception as e:
                logger(f"Error in step {step.name}: {e}")
                context.set("error", str(e))
                break
        return context
