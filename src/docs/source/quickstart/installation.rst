Installation
============

PIG is available on GitHub. To get started, clone the repository using the following command:

.. code-block:: bash

   git clone https://github.com/andthemomentoflife/artifact_pig.git

.. note::

   The repository link above is tentative and may be updated in a future release.
   Please check back for the latest URL.

Required Packages
-----------------

PIG depends on the following packages:

.. list-table::
   :widths: 20 80
   :header-rows: 1

   * - Package
     - Description
   * - ``openai``, ``ollama``
     - LLM client used to send queries to the LLM during API migration.
   * - ``jpype``
     - Enables partial transplantation of LLM-generated code by executing GumTree (made in jar file).
   * - ``asttokens``
     - Used alongside GumTree for token-level analysis during code transplantation.
   * - ``autoflake``
     - Handles post-processing of migrated code by removing unused imports and variables.
   * - ``openpyxl``
     - Required for running the actual benchmark evaluations.
   * - ``Cython``
     - Used to identify API mapping candidates when a library implementation is provided as a ``.pyc`` file.

Dependency Installation
-----------------------

You can install the dependencies in one of two ways:

**Option 1: Install all at once (recommended)**

Use the provided ``requirements.txt`` to install all packages in a single command:

.. code-block:: bash

   pip install -r requirements.txt

**Option 2: Install individually**

Alternatively, you can install each package manually:

.. code-block:: bash

   pip install openai jpype1 asttokens autoflake openpyxl Cython