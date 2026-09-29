![Version](https://img.shields.io/badge/version-0.1.3-blue)
![License](https://img.shields.io/badge/license-MIT-green)
![Tests](https://github.com/AtlasICL/whatdidi/actions/workflows/test.yml/badge.svg)
# Container block allocation program

## Overview
Custom program to optimise allocation of blocks into containers by maximal weight capacity.  
Currently in use by the client.

### Usage instructions
0. Download the executable from the latest release. 
0. Run the executable.
0. The program will require a csv file, which **must contain:**
   - 1 column with the header `BlockNo`
   - 1 column with the header `Weight` 
0. Once you provide the csv file, run the allocation!

### Executable creation instructions
```
pyinstaller --onefile --windowed --name BlockAllocator main.py
```

### Tests
```
python -m unittest discover -s test -v
```