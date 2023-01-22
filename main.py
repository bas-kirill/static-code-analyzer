PEP8_MAX_LINE_LENGTH = 79

path_to_file = input()

file = open(path_to_file)

line_number = 1
for line in file:
  if len(line) > PEP8_MAX_LINE_LENGTH:
    print(f"Line {line_number}: S001 Too long")

  line_number += 1
