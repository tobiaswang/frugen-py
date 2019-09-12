# frugen-py
tool to generate fru.bin, written in python3

how to use:
1) edit config.json
2) generate fru.bin:
  python3 frugen.py -c config.json -o fru.bin
3) optional: write fru.bin into system using ipmitool.
  ipmitool -I xxx -H xxx -U xxx -P xxx fru write 0 fru.bin
