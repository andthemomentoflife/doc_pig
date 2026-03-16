Glossary
========

Here we provide a list of commonly used terms that you will most probably encounter when reading the documentation.

----

.. glossary::

   lib
      | Abbreviation for *library* — referring to external libraries or modules used in programming.
      |

      .. list-table::
         :widths: 20 80

         * - ``libo``
           - **Source library** from which APIs are to be migrated.
         * - ``libn``
           - **Target library** to which APIs are to be migrated.

   api
      | Abbreviation for *Application Programming Interface* — a set of functions and procedures
        that allow applications to access features or data of an operating system, application, or other service.
      |

      .. list-table::
         :widths: 20 80

         * - ``apio``
           - **Source API** from *libo* that is to be migrated.
         * - ``apin``
           - **Target API** from *libn* that is to be migrated.

   code
      | Refers to the string representation of a program or snippet written in Python.
      |

      .. list-table::
         :widths: 20 80

         * - ``codeo``
           - Code snippet using the **source API** (*apio*) from *libo*.
         * - ``coden``
           - Code snippet using the **target API** (*apin*) from *libn*.

   root / tree
      | Refers to the parsed **Abstract Syntax Tree (AST)** structure of a code snippet,
        representing the hierarchical syntactic structure of the source code.
      |

      .. list-table::
         :widths: 20 80

         * - ``rooto`` / ``treeo``
           - AST structure of the **source** code snippet (*codeo*) using *apio*.
         * - ``rootn`` / ``treen``
           - AST structure of the **target** code snippet (*coden*) using *apin*.

----