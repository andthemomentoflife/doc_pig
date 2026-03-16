# Transplant 
This directory contains the source code for the transplanting process. 

# Directory Structure
### `call.py` file
This file contains the code for extracting the API calls from the source code. Moreover, it includes the code for handling the preparation of the transplanting process, such as finding the parent nodes of the API calls, extracting name nodes, and etc.

### `cens.py` file
This file contains the code for counter examples which should be handled in the transplanting process. It includes the name nodes of the APIs that is not counted as the API calls, such as `print`, `input`, and etc. This file is used to filter out the unnecessary name nodes which turn out to be unassigned variables or other non-API calls.

### `fix_import.py` file
This file contains the code for fixing the import statements in the source code(one of the PIG's post-process technique). It includes the code for finding the import statements and replacing them with the correct import statements.

### `llm_pre.py` file 
This file contains the code for auxiliary functions needed for the transplanting process.

### `main.py` file 
This file contains the main function for running the transplanting process. It includes the code for setting up the environment, loading the target files, and running the transplanting process.

### `matching.py` file
This file contains the code for matching the API calls with the target code. It includes the code for finding the target nodes, checking whether the new node is matched with the new node, and etc.

### `sketch.py` file
This file contains the main function for running the transplanting process. By executing `main.py`, it will run the functions defined in this file, which includes the process of extracting the API calls, finding the target nodes, and synthesizing the transplanting process.

### `stmt_types.`py file
This file contains the code for handling the statement types of the Python AST. 

### `sytnehsis.py` file
This file contains the code for synthesizing the transplanting process. It includes the code for replacing the API calls with the target code, inserting the new necessary nodes, and etc.

# `How to run`
To run the transplanting process, you can use the `main.py` file.
You can customize the settings in the `main.py` file, such as the target files, the model name, and the result path.

### settings
- `option = " "`: This is the settings for the transplanting process. Changing the value of the line affects which setting of LLM answer would the transplanting process use. You can set the option like below:
  - `option = "+slicing"`: This option will use the LLM answer with slicing but without API mapping.
  - `option = "default"`: This option will use the LLM answer with API mapping and slicing.
- `model = " "`: This is the model name for the LLM. You can change it to other models like `gemma`, `deepseek`, or `qwen3`. (Refer to the keys of `MODEL_NAMES` dictionary in the `main.py` file for the available models.)
- `target_files = [" "]`: This is the list of target files for the transplanting process. You can change it to the files you want to run the transplanting process on. The files should be in the `benchmarks` directory.
- Various other settings 
  - `b_varmap = True | False`: This is the setting for whether to use the variable mapping or not. If you set it to `True`, it will use the variable mapping.
  - `b_imports = True | False`: This is the setting for whether to fix the import statements or not. If you set it to `True`, it will fix the import statements.
  - `b_postprocess = True | False`: This is the setting for whether to use the post-processing techniques or not. If you set it to `True`, it will use the post-processing techniques.
  - `b_surround = True | False`: This is the setting for whether to add the additional context from the LLM code if needed. If you set it to `True`, it will add the additional context.
  - `gumtree = True | False`: This is the setting for whether to use the GumTree as a default setting or not. If you set it to `False`, it will use the default GumTree (`default.jar`).

After setting the options and running the `main.py` file, it will execute the transplanting process and save the results in the `result` directory. The results will be saved in the format of `.py` files.

### Sample Execution
To check whether the transplanting process is working correctly, you can run the `main.py` file with the default settings. It will successfully save the result in the `result` directory with the name `1.py`.

