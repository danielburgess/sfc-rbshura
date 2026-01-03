import os
import sys

# Constants from the C++ code by Proton
WINDOW_SIZE = 4096
MIN_MATCH_LENGTH = 3
MAX_MATCH_LENGTH = 18
TEST_BIT = 0x01


def check_pos(cur_pos: int) -> int:
    if cur_pos >= WINDOW_SIZE:
        cur_pos -= WINDOW_SIZE
    return cur_pos


def decompress(compressed: bytes) -> bytes:
    """
    Decompresses the given compressed data using the algorithm from the C++ code.
    Note: This assumes the input is the compressed data WITHOUT the 2-byte size header.
    It will decompress until the end of the input bytes.
    """
    comp_size = len(compressed)
    input_pos = 0
    output = bytearray()
    window = bytearray(WINDOW_SIZE)  # Initialized to 0x00
    window_pos = 0xfee

    while input_pos < comp_size:
        code = compressed[input_pos]
        input_pos += 1
        if input_pos == comp_size:
            break

        for _ in range(8):
            if (code & TEST_BIT) == TEST_BIT:
                if input_pos >= comp_size:
                    break
                lit = compressed[input_pos]
                input_pos += 1
                output.append(lit)
                window[window_pos] = lit
                window_pos = (window_pos + 1) % WINDOW_SIZE  # Equivalent to check_pos
                if input_pos == comp_size:
                    break
            else:
                if input_pos >= comp_size:
                    break
                lz1 = compressed[input_pos]
                input_pos += 1
                if input_pos >= comp_size:
                    break
                lz2 = compressed[input_pos]
                input_pos += 1
                lz_len = (lz2 & 0x0f) + MIN_MATCH_LENGTH
                lz_off = (((lz2 & 0xf0) << 4) | lz1) & 0x0fff

                for _ in range(lz_len):
                    lz_off = lz_off % WINDOW_SIZE
                    byte = window[lz_off]
                    output.append(byte)
                    window[window_pos] = byte
                    window_pos = (window_pos + 1) % WINDOW_SIZE
                    lz_off += 1

            code >>= 1

    return bytes(output)


# HiROM address conversion functions (since the game uses HiROM mapping)
def pc_to_snes_hirom(pc_offset: int) -> int:
    """
    Converts a PC file offset to a SNES address (24-bit) for HiROM.
    Assumes no header in the ROM file.
    """
    bank = 0xC0 + (pc_offset // 0x10000)
    offset = pc_offset % 0x10000
    return (bank << 16) | offset


def snes_to_pc_hirom(snes_addr: int) -> int:
    """
    Converts a SNES address (24-bit) to a PC file offset for HiROM.
    """
    bank = (snes_addr >> 16) & 0xFF
    offset = snes_addr & 0xFFFF
    if bank < 0xC0 or bank > 0xFF:
        raise ValueError("Invalid HiROM bank")
    return (bank - 0xC0) * 0x10000 + offset


# Example usage for decompressing a specific offset (like in the C++ code)
def decompress_at_offset(rom_data: bytes, pc_offset: int) -> bytes:
    # Read 2-byte compression size (little-endian)
    comp_size = (rom_data[pc_offset + 1] << 8) | rom_data[pc_offset]
    compressed = rom_data[pc_offset + 2: pc_offset + 2 + comp_size]
    return decompress(compressed)


# Function to scan for potential pointer tables and extract compressed data
def find_and_extract_compressed_sections(
        rom_file: str,
        output_dir: str = 'extracted',
        min_consecutive_valid: int = 3,  # ← lowered default + renamed for clarity
        max_comp_size: int = 0xFFFF,
        pointer_byte_sizes: list = [1, 2, 3],
        allow_non_increasing: bool = True  # ← new option
):
    with open(rom_file, 'rb') as f:
        rom = f.read()

    os.makedirs(output_dir, exist_ok=True)
    extracted = {'text': [], 'graphics': [], 'tilemap': [], 'unknown': []}

    rom_size = len(rom)

    for byte_size in pointer_byte_sizes:
        bit_size = byte_size * 8
        print(f"Scanning for {bit_size}-bit pointer tables...")
        i = 0
        while i < rom_size - byte_size * min_consecutive_valid:
            table_snes = pc_to_snes_hirom(i)
            table_bank = (table_snes >> 16) & 0xFF
            table_offset = table_snes & 0xFFFF
            table_high = (table_offset >> 8) & 0xFF

            pointers = []
            prev_pc = -1
            consecutive_valid = 0
            max_consecutive = 0
            k = 0

            while i + k * byte_size < rom_size:
                # Read pointer bytes (same as before)
                if byte_size == 3:
                    low, high, bank = rom[i + k * 3: i + k * 3 + 3]
                    snes_ptr = (bank << 16) | (high << 8) | low
                elif byte_size == 2:
                    low, high = rom[i + k * 2: i + k * 2 + 2]
                    bank = table_bank
                    snes_ptr = (bank << 16) | (high << 8) | low
                else:  # 1
                    low = rom[i + k]
                    high = table_high
                    bank = table_bank
                    snes_ptr = (bank << 16) | (high << 8) | low

                valid = False
                try:
                    pc_ptr = snes_to_pc_hirom(snes_ptr)
                    if pc_ptr < rom_size - 2:
                        # Main relaxation point
                        if allow_non_increasing or pc_ptr > prev_pc:
                            valid = True
                except ValueError:
                    pass

                if valid:
                    consecutive_valid += 1
                    max_consecutive = max(max_consecutive, consecutive_valid)
                    pointers.append(pc_ptr)
                    prev_pc = pc_ptr
                else:
                    consecutive_valid = 0
                    # Optionally: if we already have enough, we can stop early
                    if len(pointers) >= min_consecutive_valid * 2:
                        break

                k += 1

            # Decide if this is a table
            if max_consecutive >= min_consecutive_valid and len(pointers) >= min_consecutive_valid:
                print(f"Potential {bit_size}-bit pointer table at PC 0x{i:06X} "
                      f"(SNES 0x{table_snes:06X}) with {len(pointers)} valid pointers "
                      f"(max consecutive: {max_consecutive})")

                # Process pointers (same as before)
                for idx, pc_ptr in enumerate(pointers):
                    comp_size = (rom[pc_ptr + 1] << 8) | rom[pc_ptr]
                    if not (3 <= comp_size <= max_comp_size):
                        continue
                    if pc_ptr + 2 + comp_size > rom_size:
                        continue

                    compressed = rom[pc_ptr + 2: pc_ptr + 2 + comp_size]
                    try:
                        decomp = decompress(compressed)
                        if len(decomp) < 16:  # ← optional: ignore tiny output
                            continue
                    except:
                        continue

                    # classification + save (same as before)
                    printable_ratio = sum(1 for b in decomp if 0x20 <= b <= 0x7E or 0xA1 <= b <= 0xDF) / len(decomp)
                    unique_ratio = len(set(decomp)) / 256
                    category = 'unknown'
                    if printable_ratio > 0.65:
                        category = 'text'
                    elif unique_ratio > 0.75:
                        category = 'graphics'
                    elif unique_ratio < 0.40:
                        category = 'tilemap'

                    filename = f"{category}_{bit_size}bit_table_0x{i:06X}_entry{idx:03d}_ptr0x{pc_ptr:06X}.bin"
                    with open(os.path.join(output_dir, filename), 'wb') as out:
                        out.write(decomp)
                    extracted[category].append(filename)

                # Skip the whole found region
                i += len(pointers) * byte_size
            else:
                i += 1

    # Summary (same as before)
    print("\nExtracted sections:")
    for cat, files in extracted.items():
        print(f"{cat.capitalize()}: {len(files)} files")

def update_window(window: bytearray, pos_dict: dict, pos: int, byte: int, window_size: int = WINDOW_SIZE):
    mod = window_size
    starts = [(pos - 2) % mod, (pos - 1) % mod, pos]

    # Remove old tuples
    for start in starts:
        t0 = window[start]
        t1 = window[(start + 1) % mod]
        t2 = window[(start + 2) % mod]
        key = (t0, t1, t2)
        if key in pos_dict:
            try:
                pos_dict[key].remove(start)
            except ValueError:
                pass
            if not pos_dict[key]:
                del pos_dict[key]

    # Update byte
    window[pos] = byte

    # Add new tuples
    for start in starts:
        t0 = window[start]
        t1 = window[(start + 1) % mod]
        t2 = window[(start + 2) % mod]
        key = (t0, t1, t2)
        if key not in pos_dict:
            pos_dict[key] = []
        pos_dict[key].append(start)


def compress(data: bytes) -> bytes:
    """
    Compresses the given data using the matching compression algorithm.
    Returns the compressed data WITHOUT the 2-byte size header.
    """
    data_len = len(data)
    if data_len == 0:
        return b''

    window = bytearray(WINDOW_SIZE)
    window_pos = 0xfee % WINDOW_SIZE
    pos_dict = {}
    for start in range(WINDOW_SIZE):
        t0 = window[start]
        t1 = window[(start + 1) % WINDOW_SIZE]
        t2 = window[(start + 2) % WINDOW_SIZE]
        key = (t0, t1, t2)
        if key not in pos_dict:
            pos_dict[key] = []
        pos_dict[key].append(start)

    compressed = bytearray()
    input_pos = 0

    while input_pos < data_len:
        control = 0
        ops = []
        for bit_pos in range(8):
            if input_pos >= data_len:
                break

            remaining = data_len - input_pos
            if remaining < MIN_MATCH_LENGTH:
                # Literal
                lit = data[input_pos]
                ops.append(('lit', lit))
                control |= (1 << bit_pos)
                update_window(window, pos_dict, window_pos, lit)
                window_pos = (window_pos + 1) % WINDOW_SIZE
                input_pos += 1
                continue

            # Search for match
            key = (data[input_pos], data[input_pos + 1], data[input_pos + 2])
            candidates = pos_dict.get(key, [])
            max_len = MIN_MATCH_LENGTH - 1
            best_off = -1

            for off in candidates:
                match_len = MIN_MATCH_LENGTH
                while (
                    match_len < MAX_MATCH_LENGTH
                    and input_pos + match_len < data_len
                    and data[input_pos + match_len] == window[(off + match_len) % WINDOW_SIZE]
                ):
                    match_len += 1
                if match_len > max_len:
                    max_len = match_len
                    best_off = off

            if max_len >= MIN_MATCH_LENGTH:
                # LZ copy
                lz_len = max_len
                lz_off = best_off
                len_code = lz_len - MIN_MATCH_LENGTH
                off_code = lz_off & 0x0FFF
                lz1 = off_code & 0xFF
                lz2 = ((off_code >> 8) << 4) | len_code
                ops.append(('lz', lz1, lz2))
                # bit remains 0
                # Update window
                for j in range(lz_len):
                    byte = window[(best_off + j) % WINDOW_SIZE]
                    update_window(window, pos_dict, window_pos, byte)
                    window_pos = (window_pos + 1) % WINDOW_SIZE
                input_pos += lz_len
            else:
                # Literal
                lit = data[input_pos]
                ops.append(('lit', lit))
                control |= (1 << bit_pos)
                update_window(window, pos_dict, window_pos, lit)
                window_pos = (window_pos + 1) % WINDOW_SIZE
                input_pos += 1

        # Append to compressed
        compressed.append(control)
        for op in ops:
            if op[0] == 'lit':
                compressed.append(op[1])
            else:
                compressed.append(op[1])
                compressed.append(op[2])

    return bytes(compressed)


def compress_and_add_header(data: bytes) -> bytes:
    compressed = compress(data)
    size = len(compressed)
    header = bytes([size & 0xFF, (size >> 8) & 0xFF])
    return header + compressed

# Example: Decompress the specific section from the C++ code
# rom_data = open('Rushing Beat Shura (J) [!].sfc', 'rb').read()
# decomp = decompress_at_offset(rom_data, 0x182A43)
# open('decomp.bin', 'wb').write(decomp)

# To scan and extract:
# find_and_extract_compressed_sections('Rushing Beat Shura (J) [!].sfc')

# Example:
# rom_data = open('Rushing Beat Shura (J) [!].sfc', 'rb').read()
# decomp = decompress_at_offset(rom_data, 0x182A43)
# recomp = compress(decomp)
# decomp_again = decompress(recomp)
# assert decomp == decomp_again
# # To insert back, compute the header + recomp, but size may differ from original
