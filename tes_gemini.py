import os
import re
import time
import traceback
import google.generativeai as genai # changed import name
from google.generativeai import types

# --- MODEL CONFIGURATION ---
# Using the model name you provided and adding other common Gemini models
MODELS_TO_TEST = [
    "gemini-2.5-flash-preview-04-17", # Fast and efficient
    "gemini-2.5-flash-lite-preview-06-17",   # More capable, higher cost
    "gemini-2.5-flash",
    "gemini-2.0-flash"
                  # The model name you provided (ensure you have access to it)
]

# --- GEMINI CLIENT INITIALIZATION ---
try:
    # The configure method has been deprecated
    # We will configure the API key directly on the genai module
    genai.configure(api_key=os.environ.get("GEMINI_API_KEY"))

    # The client object is not typically initialized directly with `genai.Client`
    # when using `genai.configure`. Instead, models are accessed via `genai.GenerativeModel`.
except Exception as e:
    print("Error configuring Gemini client. Make sure your GEMINI_API_KEY is set.")
    print(e)
    exit()

# --- PROMPT ENGINEERING ---
# This prompt is designed to force the model to only output code
def get_coding_prompt(question_description, function_name, args):
    return f"""You are an expert Python programmer. Your task is to solve the following programming problem.
Your response MUST be a single, complete Python code block.
You MUST NOT include any text, explanation, or comments outside of the code block.
The function must be named `{function_name}` and take the arguments `{', '.join(args)}`.
Do not include any example usage or `if __name__ == "__main__":` block.

Problem Description:
---
{question_description}
---
"""

# --- CODE EXTRACTION ---
def extract_python_code(response_content):
    """Extracts Python code from a markdown-formatted string."""
    code_block_match = re.search(r"```python\n(.*?)\n```", response_content, re.DOTALL)
    if code_block_match:
        return code_block_match.group(1).strip()
    # Fallback for models that might not use markdown (less common for code-focused models)
    return response_content.strip()

# --- BENCHMARKING QUESTIONS AND TEST CASES ---

class TestQuestion:
    def __init__(self, name, description, function_name, args, test_cases):
        self.name = name
        self.description = description
        self.function_name = function_name
        self.args = args
        self.test_cases = test_cases

    def get_prompt(self):
        return get_coding_prompt(self.description, self.function_name, self.args)

    def run_tests(self, generated_code):
        passed_count = 0
        try:
            # Execute the generated code to define the function
            exec_globals = {}
            exec(generated_code, exec_globals)
            solution_func = exec_globals.get(self.function_name)

            if not solution_func:
                # The model did not generate the function with the correct name
                return 0, f"Function '{self.function_name}' not found."

            for i, (inputs, expected_output) in enumerate(self.test_cases):
                try:
                    # The inputs tuple needs to be unpacked for the function call
                    actual_output = solution_func(*inputs)
                    if actual_output == expected_output:
                        passed_count += 1
                    # Special handling for Question 5 which has two functions
                    elif self.name == "Q5: Serialize/Deserialize Tree":
                         # This case is special, we need to serialize then deserialize
                         deserializer = exec_globals.get("deserialize")
                         if deserializer:
                             serialized_data = solution_func(inputs[0])
                             reconstructed_tree = deserializer(serialized_data)
                             # A simple check for structural equality
                             if serialize_tree_for_check(reconstructed_tree) == serialize_tree_for_check(inputs[0]):
                                 passed_count += 1
                except Exception as e:
                    # A single test case failure shouldn't stop the whole run
                    # print(f"      Test case {i+1} failed with error: {e}")
                    pass # Just count it as a fail

            return passed_count, f"Passed {passed_count}/{len(self.test_cases)}"

        except Exception as e:
            return 0, f"Code execution failed: {traceback.format_exc()}"


# --- Helper classes/functions for test cases ---
class TreeNode:
    def __init__(self, val=0, left=None, right=None):
        self.val = val
        self.left = left
        self.right = right

def serialize_tree_for_check(root):
    # A consistent way to check tree equality for the test harness
    if not root:
        return "[]"
    res = []
    q = [root]
    while q:
        node = q.pop(0)
        if node:
            res.append(str(node.val))
            q.append(node.left)
            q.append(node.right)
        else:
            res.append("null")
    # Trim trailing nulls
    while res and res[-1] == "null":
        res.pop()
    return f"[{','.join(res)}]"


# --- DEFINE ALL QUESTIONS AND THEIR TEST CASES ---
def get_all_questions():
    # --- Question 1 ---
    q1_desc = "Given a 2D grid where each cell has a cost to enter, and a separate list of 'toll booth' cells `(row, col)` that incur an additional fixed toll cost, find the minimum cost path from the top-left corner `(0, 0)` to the bottom-right corner `(rows-1, cols-1)`. You can only move right or down."
    q1_tests = [
        # ( (grid, tolls, toll_cost), expected_output )
        ( ([[1, 3, 1], [1, 5, 1], [4, 2, 1]], [], 10), 7), # Simple case, no tolls
        ( ([[1, 3, 1], [1, 5, 1], [4, 2, 1]], [(1, 1)], 10), 17), # One toll on the optimal path
        ( ([[1, 1, 1], [10, 10, 1], [1, 10, 1]], [(0, 1)], 5), 10), # Toll forces a detour
        ( ([[1]], [], 100), 1), # Single cell grid
        ( ([[1, 1, 1, 1]], [], 10), 4), # Single row grid
        ( ([[1], [1], [1], [1]], [], 10), 4), # Single column grid
        ( ([[1, 100], [1, 1]], [(0, 0)], 5), 8), # Toll at the start
        ( ([[1, 1], [100, 1]], [(1, 1)], 5), 8), # Toll at the end
        ( ([[1, 2, 3], [4, 5, 6], [7, 8, 9]], [(0, 1), (1, 1), (2, 1)], 10), 31), # Multiple tolls
        ( ([[10, 1], [1, 10]], [], 10), 12) # Simple choice
    ]
    q1 = TestQuestion("Q1: Grid Path with Tolls", q1_desc, "min_path_cost", ["grid", "tolls", "toll_cost"], q1_tests)

    # --- Question 2 ---
    q2_desc = "Given a string `s`, find the length of the longest palindromic subsequence in it. A subsequence is a sequence that can be derived from another sequence by deleting some or no elements without changing the order of the remaining elements."
    q2_tests = [
        ( ("bbbab",), 4 ), # "bbbb"
        ( ("cbbd",), 2 ), # "bb"
        ( ("a",), 1 ),
        ( ("",), 0 ),
        ( ("agbdba",), 5 ), # "abdba"
        ( ("abcdefg",), 1 ),
        ( ("aaaaa",), 5 ),
        ( ("abacaba",), 7 ),
        ( ("character",), 5 ), # "carac"
        ( ("topcoderopen",), 3) # "opo"
    ]
    q2 = TestQuestion("Q2: Longest Palindromic Subsequence", q2_desc, "longest_palindrome_subseq", ["s"], q2_tests)

    # --- Question 3 ---
    q3_desc = "Given a nested list of integers, return the sum of all integers in the list weighted by their depth, but with the weighting reversed. The leaf-level integers have a weight of 1, and the root-level integers have the highest weight. For example, in `[[1,1],2,[1,1]]`, the `1`s are at depth 2 and the `2` is at depth 1. The max depth is 2. So, the `2` gets weight `(2-1+1)=2` and the `1`s get weight `(2-2+1)=1`. The result is `(1*1 + 1*1 + 1*1 + 1*1) + (2*2) = 8`."
    q3_tests = [
        ( ([[1,1],2,[1,1]],), 8 ),
        ( ([1,[4,[6]]],), 17 ), # 1*(3-1+1) + 4*(3-2+1) + 6*(3-3+1) = 3 + 8 + 6 = 17
        ( ([1],), 1 ),
        ( ([],), 0 ),
        ( ([[[1]]],), 1 ),
        ( ([1, 2, 3],), 6 ), # All at depth 1, max depth 1. 1*1 + 2*1 + 3*1 = 6
        ( ([[1], [1]],), 2 ),
        ( ([[[[[5]]]]],), 5 ),
        ( ([6, [4, [2]]],), 28 ), # max_depth=3. 6:(d=1,w=3), 4:(d=2,w=2), 2:(d=3,w=1) => 6*3+4*2+2*1 = 18+8+2 = 28.
        ( ([2, [3, [4, 5]]],), 21 ) # max_depth=3. 2:(d=1,w=3), 3:(d=2,w=2), 4:(d=3,w=1), 5:(d=3,w=1) => 2*3 + 3*2 + 4*1 + 5*1 = 6+6+4+5=21.
    ]
    q3 = TestQuestion("Q3: Nested List Weight Sum II", q3_desc, "depth_sum_inverse", ["nested_list"], q3_tests)


    # --- Question 4 ---
    q4_desc = 'Implement a function that simulates a single move in a classic Snake game. The function takes the board dimensions (`width`, `height`), the current snake\'s body coordinates (a list of `[x, y]` pairs, with the head at index 0), the current food location `[x, y]`, and the next move ("U", "D", "L", "R"). The function should return the new state of the snake\'s body. The game ends if the snake hits a wall or itself. In case the game ends, return the string "Game Over".'
    q4_tests = [
        # ( (width, height, snake_body, food_loc, move), expected_output )
        ( (10, 10, [[2,2], [2,1]], [5,5], "U"), [[2,3], [2,2]] ), # Move up
        ( (10, 10, [[2,2], [2,1]], [3,2], "R"), [[3,2], [2,2], [2,1]] ), # Move right and eat food
        ( (5, 5, [[4,2], [3,2]], [0,0], "R"), "Game Over" ), # Hit right wall
        ( (5, 5, [[0,2], [1,2]], [3,3], "L"), "Game Over" ), # Hit left wall
        ( (5, 5, [[2,4], [2,3]], [3,3], "U"), "Game Over" ), # Hit top wall
        ( (5, 5, [[2,0], [2,1]], [3,3], "D"), "Game Over" ), # Hit bottom wall
        ( (5, 5, [[2,2], [2,1], [3,1], [3,2]], [4,4], "L"), "Game Over" ), # Self collision
        ( (3, 3, [[0,0]], [1,0], "R"), [[1,0],[0,0]] ), # 1-segment snake eats food
        ( (20, 20, [[10,10]], [5,5], "D"), [[10,9]] ), # 1-segment snake moves down
        ( (5, 5, [[2,2], [2,1], [1,1]], [2,3], "U"), [[2,3], [2,2], [2,1], [1,1]] ) # Move up and eat food
    ]
    q4 = TestQuestion("Q4: Snake Game Simulator", q4_desc, "simulate_snake_move", ["width", "height", "snake_body", "food_loc", "move"], q4_tests)

    # --- Question 5 ---
    # For this one, the test harness is special. It checks serialize(deserialize(data)) == data
    q5_desc = "Design an algorithm to serialize a binary tree to a single string and deserialize the string back to the original tree structure. You must implement two functions: `serialize(root)` and `deserialize(data)`. The test harness will verify that `deserialize(serialize(root))` results in an identical tree. Handle `None` nodes."
    # ( (root_node,), expected_output_is_same_tree )
    # The expected output is the same as the input tree, the harness handles the check.
    t1 = TreeNode(1, TreeNode(2), TreeNode(3, TreeNode(4), TreeNode(5)))
    t2 = None
    t3 = TreeNode(1)
    t4 = TreeNode(1, TreeNode(2))
    t5 = TreeNode(1, None, TreeNode(2))
    t6 = TreeNode(5, TreeNode(4, TreeNode(11, TreeNode(7), TreeNode(2))), TreeNode(8, TreeNode(13), TreeNode(4, None, TreeNode(1))))
    t7 = TreeNode(-1, TreeNode(0), TreeNode(1))
    t8 = TreeNode(2, TreeNode(1), TreeNode(3))
    t9 = TreeNode(1, TreeNode(2, TreeNode(3, TreeNode(4))))
    t10 = TreeNode(1,None,TreeNode(2,None,TreeNode(3,None,TreeNode(4))))

    # We use serialize_tree_for_check to get a comparable value
    q5_tests = [((t,) , serialize_tree_for_check(t)) for t in [t1,t2,t3,t4,t5,t6,t7,t8,t9,t10]]
    q5 = TestQuestion("Q5: Serialize/Deserialize Tree", q5_desc, "serialize", ["root"], q5_tests)

    return [q1, q2, q3, q4, q5]

# --- MAIN EXECUTION ---
if __name__ == "__main__":
    questions = get_all_questions()
    results = {model: {} for model in MODELS_TO_TEST}
    total_scores = {model: 0 for model in MODELS_TO_TEST}

    print("Starting Gemini Coding Benchmark...")
    print(f"Models to test: {', '.join(MODELS_TO_TEST)}\n")

    for model_name in MODELS_TO_TEST:
        print(f"--- Testing Model: {model_name} ---")
        try:
            # Initialize the model instance for the current model_name
            # For `google-genai`, you typically get the model object this way
            model_instance = genai.GenerativeModel(model_name)
        except Exception as e:
            print(f"  Could not load model {model_name}: {e}")
            print("  Skipping this model.")
            continue # Skip to the next model if it can't be loaded

        for q in questions:
            print(f"  > Running {q.name}...")
            start_time = time.time()
            try:
                # Construct the content for the Gemini API call
                contents_parts = [q.get_prompt()]

                # Generate content using the non-streaming method for full response
                response = model_instance.generate_content(
                    contents_parts,
                    generation_config=types.GenerationConfig(
                        temperature=0.0, # Setting temperature to 0 for more deterministic output
                    ),
                    # thinking_config = types.ThinkingConfig(thinking_budget=-1), # Optional, can be included if desired
                )

                response_content = response.text # Get the text directly
                generated_code = extract_python_code(response_content)

                if not generated_code:
                    score, message = 0, "No code was generated."
                else:
                    score, message = q.run_tests(generated_code)

                total_scores[model_name] += score
                results[model_name][q.name] = score

            except Exception as e:
                score, message = 0, f"API call failed: {e}"
                # For more detailed error if needed:
                # print(f"  API Error for {q.name}: {e}\n{traceback.format_exc()}")
                results[model_name][q.name] = 0

            end_time = time.time()
            print(f"    Result: {message} ({end_time - start_time:.2f}s)")

    print("\n\n--- Benchmark Complete ---")
    print("--- Final Leaderboard ---\n")

    # Prepare header
    header = f"| {'Model':<45} |"
    for q in questions:
        header += f" {q.name.split(':')[0]:<4} |"
    header += " Total Score |"
    print(header)
    print(f"|{'-'*47}|{'-'*6}|{'-'*6}|{'-'*6}|{'-'*6}|{'-'*6}|{'-'*13}|")

    # Sort models by total score
    sorted_models = sorted(total_scores.items(), key=lambda item: item[1], reverse=True)

    for model_name, total_score in sorted_models:
        row = f"| {model_name:<45} |"
        for q in questions:
            score = results[model_name].get(q.name, 0)
            row += f" {score:>2}/10 |"
        row += f" {total_score:>11} |"
        print(row)