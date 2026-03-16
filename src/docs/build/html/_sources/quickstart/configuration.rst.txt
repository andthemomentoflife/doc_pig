Configuration
=============

PIG requires a small amount of configuration before use, depending on which LLM backend you choose and whether you want to use the API mapping module. Below are the details on how to set up these configurations.

LLM Backend
-----------

PIG supports two LLM backends: **OpenAI** and **Ollama**.
You can specify the backend by passing it directly to the relevant function,
while the corresponding credentials are read from environment variables.

**Using OpenAI**

Set your OpenAI API key as an environment variable:

.. code-block:: bash

   export OPENAI_API_KEY="your-openai-api-key"

**Using Ollama**

Set the Ollama host address as an environment variable:

.. code-block:: bash

   export OLLAMA_HOST="http://localhost:11434"

Then pass the backend to the function:

.. warning::

   Never hard-code your API key in your source code.
   Always use environment variables to keep credentials secure.


Library Implementation Directory
---------------------------------

PIG includes an API mapping module that identifies candidate mappings between APIs in the source and target libraries.
During this process, PIG references the implementation of the source and/or target library.
Therefore, set the path to the directory containing the library implementations as an environment variable:

.. code-block:: bash

   export PIG_LIB_DIR="/path/to/library-repos"

.. note::

   The directory should contain one subdirectory per library, named exactly after the library.
   An example structure is as follows:

   .. code-block:: text

      library-repos/
      ├── source-library/
      │   ├── __init__.py
      │   ├── module1.py
      │   └── module2.py
      └── target-library/
          ├── __init__.py
          ├── moduleA.py
          └── moduleB.py

   The name of each subdirectory (e.g., ``source-library``, ``target-library``) must match
   the name of the library you are migrating from or to.

   In Python, you can retrieve this value via:

   .. code-block:: python

      import os
      lib_dir = os.environ.get("PIG_LIB_DIR")

Registering Library Source Paths
----------------------------------

Some libraries have their Python source files located in a specific subdirectory within the repository.
To let PIG know where to look, you need to register the path for each library in ``src/pig/mapping/gits.py``.

Add an entry to the ``GIT_LOC`` dictionary, where the key is the library name and the value is the relative path
from ``PIG_LIB_DIR`` to the directory containing the actual Python source files:

.. code-block:: python

   # src/pig/mapping/gits.py

   GIT_LOC = {
       "unipath": "Unipath-master/unipath",
       "library-name: "library-repo/src",  # add your entry here
   }

.. note::

   If a library's Python files are located directly in the root of its subdirectory,
   you can simply use the file name as the value (e.g., ``"mylib": "mylib.py"``).