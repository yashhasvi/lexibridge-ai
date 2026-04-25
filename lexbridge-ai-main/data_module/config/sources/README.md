# Folder: sources

## Overview

This folder contains the following files and their summaries.

## Files

### wikidata.yaml

# File: wikidata.yaml

## Purpose
Configures the import of Wikidata data into the system.

## Key Components
* `dump_base_url` and `dump_filename`: URLs for downloading Wikidata dumps.
* `min_sitelinks`, `require_english_label`: Filters entities to keep only those with at least one sitelink and an English label.
* `properties_to_extract`: List of Wikidata properties to extract as triples.

## Important Logic
The configuration assumes that the latest dump is downloaded from the specified URL and uncompressed. The filter settings (`min_sitelinks`, `require_english_label`) are used to select a subset of entities for import.

## Dependencies
None noted in this file, but likely depends on other configuration files or system dependencies.

## Notes
* The recommended configuration keeps only items with English labels and at least one sitelink.
* The dump is compressed (~100 GB) so filtering to smaller subsets may be beneficial.

---

### natural_questions.yaml

# File: natural_questions.yaml

## Purpose
Load Natural Questions dataset from Hugging Face, with Google search queries and Wikipedia answers.

## Key Components
* `huggingface_id`: ID of the dataset on Hugging Face
* `use_simplified`: Flag to enable simplified loading (default: true)
* `splits`: Available splits for training and validation
* `max_rows`: Maximum number of rows to load per split (set to 50k for memory efficiency)
* `read_columns`: Only load specified columns from Parquet file

## Important Logic
None, this is a configuration file.

## Dependencies
Hugging Face datasets library (`huggingface_id` property)

## Notes
The dataset has a CC BY-SA 3.0 license and attribution should be given to the original authors at https://ai.google.com/research/NaturalQuestions.

---

### squad.yaml

# File: squad.yaml

## Purpose
SQuAD 2.0 dataset configuration file for reading comprehension over Wikipedia paragraphs.

## Key Components
* `huggingface_id`: SQuAD 2.0 dataset identifier on Hugging Face.
* `splits`: Training and validation split configurations.
* `include_unanswerable`: Flag to include unanswerable questions in the dataset (set to `true` for SQuAD 2.0).

## Important Logic
None

## Dependencies
* Hugging Face library.

## Notes
The dataset is licensed under CC BY-SA 4.0, and attribution should be given using a provided template URL.

---

### triviaqa.yaml

# File: triviaqa.yaml

## Purpose
Trivia QA model configuration file, using Hugging Face's `mandarjoshi/trivia_qa` model with web and Wikipedia evidence.

## Key Components
* Model: `mandarjoshi/trivia_qa`
* Configuration: `rc.wikipedia` (or `rc.web`, `unfiltered.nocontext`)
* Dataset splits: `train`, `validation`

## Important Logic
The model includes evidence documents alongside the QA pairs, as specified by `include_evidence: true`.

## Dependencies
Hugging Face's `mandarjoshi/trivia_qa` model and Wikipedia API.

## Notes
Licensed under Apache 2.0 license. Attribution template provided for citing the model.

---

### hotpotqa.yaml

# File: hotpotqa.yaml

## Purpose
Define configuration for the HotPotQA dataset, a multi-hop reasoning QA task that requires two Wikipedia paragraphs per question.

## Key Components
* `huggingface_id`: ID of the dataset on Hugging Face
* `config`: Configuration type (e.g. "fullwiki" or "distractor")
* `splits`: Training and validation splits
* `include_levels`: Difficulty levels to include in the dataset

## Important Logic
The configuration requires two Wikipedia paragraphs per question, and supports difficulty levels (easy, medium, hard).

## Dependencies
None specified.

## Notes
The dataset is licensed under CC BY-SA 4.0 and attribution is required with a template provided on the HotPotQA website.

---

### stackexchange.yaml

# File: stackexchange.yaml

## Purpose
This YAML file configures a download process for Stack Exchange data from the Internet Archive.

## Key Components
* `archive_base_url`: The base URL for downloading archives.
* `sites`: A list of specific sites to download, or an empty list to download all ~200 sites.
* `post_fields`: Fields to extract from Posts.xml files.
* `min_question_score` and `min_answer_score`: Filters out low-quality questions and answers.

## Important Logic
The file filters out very low quality posts (defined by score) and excludes comments. It also specifies the license and attribution template for downloaded data.

## Dependencies
None explicitly stated, but likely requires access to Internet Archive and Stack Exchange archives.

## Notes
This configuration predates the LLM-training gate and uses a specific mirror of the Internet Archive.

---

### wikipedia.yaml

# File: wikipedia.yaml

## Purpose
This file defines a configuration for Wikipedia dataset from Hugging Face, specifically a subset of the wikimedia/wikipedia 20231101.en dump.

## Key Components
- **Hugging Face ID**: `wikimedia/wikipedia`
- **Config**: `20231101.en`
- **Streaming Mode**: Enabled (`streaming: true`)

## Important Logic
The configuration reads a subset of Wikipedia articles, filtering by length (`min_article_length: 200`) and uses the `WikipediaMapper` to select specific fields (`id`, `title`, `text`, `url`). It does not cache the full dataset on disk.

## Dependencies
- **Hugging Face**: For accessing the wikimedia/wikipedia dataset

## Notes
This configuration is designed for streaming, aiming for good performance with minimal memory usage.

---

### openassistant.yaml

# File: openassistant.yaml

## Purpose
The purpose of this file is to define a configuration for the OpenAssistant model.

## Key Components
* `openassistant`: The main configuration section.
* `huggingface_id`: Specifies the ID of the OpenAssistant model in Hugging Face's model repository.
* `splits`: Defines two splits: `train` and `validation`.
* `include_languages`: Specifies a list of languages to include (default is all languages).
* `min_quality_score` and `max_toxicity_score`: Filter messages based on quality and toxicity scores.

## Important Logic
The file uses Hugging Face's model repository to specify the OpenAssistant model. It also filters messages based on quality and toxicity scores.

## Dependencies
* Apache 2.0 license.
* Hugging Face's model repository (specified by `huggingface_id`).

## Notes
The file is part of a larger configuration file that defines the data splits and filtering criteria for the OpenAssistant model.

---

### local_file.yaml

# File: local_file.yaml

## Purpose
This YAML file defines the configuration for processing local files, specifically CSV or JSON files under `data/raw/local_file/`. It enables full pipeline processing (Parquet, LanceDB, graph, etc.).

## Key Components
- `seed_files`: An empty list to copy bundled samples from `data_module/sample_data/`.
- `extra_import`: A list of repository-relative imports from `config/sources/` or other locations.
- `column_mapping`: Maps column names to specific fields (qid, subject, body, category, answer, topic, keywords) for CQA-style CSV files.

## Important Logic
The configuration allows two methods to add files:
1. Dropping CSV/JSON files directly into `data/raw/local_file/`.
2. Listing paths in the `extra_import` section relative to the YAML file's directory.

## Dependencies
- The configuration relies on the existence of files under `data_module/sample_data/` and `config/sources/`.

## Notes
- The column mapping is specific for CQA-style CSV files, but can be adjusted for other shapes.
- The license and language are set as unknown and English, respectively.

---

### ms_marco.yaml

# File: ms_marco.yaml

## Purpose
The file defines configuration settings for the MS MARCO passage QA dataset.

## Key Components
* `huggingface_id`: The Hugging Face model ID, set to "microsoft/ms_marco"
* `config`: The model configuration, set to "v2.1"
* `splits`: Specifies the training and validation datasets

## Important Logic
The `max_rows` setting is capped at 100000 to prevent excessive disk usage.

## Dependencies
None specified in the file content.

## Notes
* The dataset is licensed under CC BY 4.0.
* Attribution should be given to Microsoft at msmarco.org.
* Commercial use requires checking underlying document rights.

---

