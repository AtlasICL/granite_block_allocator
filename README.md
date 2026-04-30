## Container block allocation program
Author: Emre Acarsoy

### Overview
Custom program to optimise allocation of blocks into containers by maximal weight capacity.  

### Usage instructions
0. Download the executable from the latest release. 
0. Run the executable.
0. The program will require a csv file, which **must contain:**
   - 1 column with the header `BlockNo`
   - 1 column with the header `Weight` 
0. Once you provide the csv file, run the allocation!

### Development
Windows executable build command:
```
pyinstaller --onefile --windowed --name BlockAllocator main.py
```