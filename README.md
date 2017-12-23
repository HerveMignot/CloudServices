# CloudServices
Utilities for various cloud services

## Convert speech to text

Usage: convert2txt filename

Convert sound file to text.

optional arguments:
  -h, --help            show this help message and exit

Conversion:
  Run file conversion on API

  soundfile             sound file name
  -l LANGUAGE, --language LANGUAGE
                        language (default en-US)
  --nowait              do not wait for results, return operation name
  --keep                keep uploaded file in the bucket

Retrieve:
  Retrieve results from API

  --get OPERATION_NAME  get results from operation

