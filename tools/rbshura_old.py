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
def pc_to_snes_hirom(pc_offset: int, output_hex_str: bool = False) -> int | str:
    """
    Converts a PC file offset to a SNES address (24-bit) for HiROM.
    Assumes no header in the ROM file.
    """
    bank = 0xC0 + (pc_offset // 0x10000)
    offset = pc_offset % 0x10000
    if output_hex_str:
        return f'{(bank << 16) | offset:#x}'
    return (bank << 16) | offset


def snes_to_pc_hirom(snes_addr: int, output_hex_str: bool = False) -> int | str:
    """
    Converts a SNES address (24-bit) to a PC file offset for HiROM.
    """
    bank = (snes_addr >> 16) & 0xFF
    offset = snes_addr & 0xFFFF
    if bank < 0xC0 or bank > 0xFF:
        raise ValueError("Invalid HiROM bank")
    if output_hex_str:
        return f'{(bank - 0xC0) * 0x10000 + offset:#x}'
    return (bank - 0xC0) * 0x10000 + offset


# Example usage for decompressing a specific offset (like in the C++ code)
def decompress_at_offset(rom_data: bytes, pc_offset: int) -> bytes:
    # Read 2-byte compression size (little-endian)
    comp_size = (rom_data[pc_offset + 1] << 8) | rom_data[pc_offset]
    compressed = rom_data[pc_offset + 2: pc_offset + 2 + comp_size]
    return decompress(compressed)


def decompress_file_at_offset(file_path: str, pc_offset: int, output_dir: str = 'decompressed') -> bytes:
    with open(file_path, 'rb') as f:
        file_data = f.read()
    decompressed = decompress_at_offset(file_data, pc_offset)

    os.makedirs(output_dir, exist_ok=True)
    with open(output_dir + '/' + f'{pc_offset:#x}.bin', 'wb') as f:
        f.write(decompressed)


def compress_file(file_path: str, output_dir: str = 'compressed'):
    os.makedirs(output_dir, exist_ok=True)

    with open(file_path, 'rb') as f:
        file_data = f.read()
    compressed = compress_lz(file_data)
    with open(output_dir + '/' + os.path.basename(file_path), 'wb') as f:
        f.write(compressed)


# Function to scan for potential pointer tables and extract compressed data
def find_and_extract_compressed_sections(rom_file: str, output_dir: str = 'extracted', min_consecutive_valid: int = 3,
                                         max_comp_size: int = 0xFFFF, pointer_byte_sizes: list = [2, 3],
                                         allow_non_increasing: bool = True, max_table_bytes: int = 0x8000):
    """
    Scans the ROM for potential pointer tables of different sizes (8-bit/1-byte, 16-bit/2-byte, 24-bit/3-byte).
    For each potential table, follows pointers, checks for compression header, decompresses if valid,
    and attempts basic classification (text/graphics/tilemap).
    Outputs decompressed files to output_dir, sorted by type if possible.

    For 16-bit pointers: Assumes bank is the same as the table's bank.
    For 8-bit pointers: Assumes bank same as table, and high byte same as table's offset high byte (same page).
    For 24-bit: Explicit bank.

    Classification heuristics (basic and imperfect):
    - Text: High proportion of printable ASCII/JP chars (0x20-0x7E, 0xA1-0xDF for Shift-JIS half-width).
    - Graphics: High entropy (diverse byte values, no long runs).
    - Tilemap: Repeating patterns or low byte variety (e.g., tile indices).

    Note: This is a heuristic scan; false positives possible. Adjust min_consecutive_valid for sensitivity.
    """
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
            k = 0

            while i + k * byte_size < rom_size and k * byte_size < max_table_bytes:
                # Read pointer bytes
                if byte_size == 3:
                    low, high, bank = rom[i + k * 3: i + k * 3 + 3]
                    if len(rom[i + k * 3: i + k * 3 + 3]) < 3:
                        break
                    snes_ptr = (bank << 16) | (high << 8) | low
                elif byte_size == 2:
                    low_high = rom[i + k * 2: i + k * 2 + 2]
                    if len(low_high) < 2:
                        break
                    low, high = low_high
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
                        if allow_non_increasing or pc_ptr > prev_pc:
                            valid = True
                except ValueError:
                    pass

                if valid:
                    pointers.append(pc_ptr)
                    prev_pc = pc_ptr
                    k += 1
                else:
                    break  # Stop at first invalid; only contiguous valid pointers

            # Decide if this is a table
            if len(pointers) >= min_consecutive_valid:
                print(
                    f"Potential {bit_size}-bit pointer table at PC 0x{i:06X} (SNES 0x{table_snes:06X}) with {len(pointers)} entries")

                # Now process each pointer
                for idx, pc_ptr in enumerate(pointers):
                    # Read compression size
                    comp_size = (rom[pc_ptr + 1] << 8) | rom[pc_ptr]
                    if comp_size == 0 or comp_size > max_comp_size or pc_ptr + 2 + comp_size > rom_size:
                        continue  # Invalid

                    compressed = rom[pc_ptr + 2: pc_ptr + 2 + comp_size]
                    try:
                        decomp = decompress(compressed)
                        if len(decomp) == 0:
                            continue
                    except IndexError:
                        continue  # Decompression failed

                    # Basic classification
                    decomp_str = decomp.decode('shift-jis', errors='ignore')
                    printable_ratio = sum(1 for b in decomp if 0x20 <= b <= 0x7E or 0xA1 <= b <= 0xDF) / len(
                        decomp) if decomp else 0
                    unique_bytes = len(set(decomp)) / 256 if decomp else 0
                    category = 'unknown'
                    if printable_ratio > 0.7:
                        category = 'text'
                    elif unique_bytes > 0.8:  # High variety -> graphics?
                        category = 'graphics'
                    elif unique_bytes < 0.3:  # Low variety -> tilemap?
                        category = 'tilemap'

                    # Save
                    filename = f"{category}_{bit_size}bit_table_at_0x{i:06X}_entry_{idx:02d}_ptr_0x{pc_ptr:06X}.bin"
                    with open(os.path.join(output_dir, filename), 'wb') as out:
                        out.write(decomp)
                    extracted[category].append(filename)

                i += len(pointers) * byte_size  # Skip the table
            else:
                i += 1  # Continue scanning

    # Summary
    print("\nExtracted sections:")
    for cat, files in extracted.items():
        print(f"{cat.capitalize()}: {len(files)} files")
        for f in files:
            print(f" - {f}")


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


def decompress_rle_16(data: bytes) -> bytes:
    """
    Decompress very simple repeating pattern RLE used in your data.
    Pattern: xx ?F  → repeat byte xx   (ord(?)+1) * 16 times
    All other bytes are copied literally.
    """
    result = bytearray()
    i = 0
    length = len(data)

    while i < length:
        b = data[i]

        # Check if we have at least 2 bytes left and second byte ends with 0xF
        if i + 1 < length and (data[i + 1] & 0x0F) == 0x0F:
            control = data[i + 1]
            repeat_count = ((control >> 4) + 1) * 16
            result.extend([b] * repeat_count)
            i += 2  # skip both bytes
        else:
            # literal byte
            result.append(b)
            i += 1

    return bytes(result)


def compress_rle_16(data: bytes, min_repeat: int = 12) -> bytes:
    """
    Very simple compressor that tries to recreate similar style of compression.
    Only compresses runs >= min_repeat (tune this value).
    Uses format: byte + control_byte (N f) where repeat = (N+1)*16
    """
    if not data:
        return b''

    result = bytearray()
    i = 0
    n = len(data)

    while i < n:
        current = data[i]
        count = 1
        i += 1

        while i < n and data[i] == current:
            count += 1
            i += 1

        # Try to compress only longer runs
        if count >= min_repeat:
            # Find largest multiple of 16 we can encode
            units = count // 16
            remainder = count % 16

            while units > 0:
                # max we can encode in one control byte is 16*16 = 256 (F → 16×16)
                take_units = min(units, 16)
                control = ((take_units - 1) << 4) | 0x0F
                result.extend([current, control])
                units -= take_units

            # remainder as literals
            if remainder:
                result.extend([current] * remainder)
        else:
            # short run → just literals
            result.extend([current] * count)

    return bytes(result)


def compress_lz(data: bytes) -> bytes:
    out = bytearray()
    i = 0

    while i < len(data):
        # Zero run
        if data[i] == 0:
            j = i
            while j < len(data) and data[j] == 0 and j - i < 0xFFFF:
                j += 1
            count = j - i
            out.extend([0x00, count & 0xFF, (count >> 8) & 0xFF])
            i = j
            continue

        # Literal block
        j = i
        while j < len(data) and data[j] != 0 and j - i < 0x7F:
            j += 1
        block = data[i:j]
        out.append(len(block))
        out.extend(block)
        i = j

    return bytes(out)


def decompress_rle_16_file(input_path: str, output_path: str) -> None:
    """
    Decompress a file using the RLE-16 scheme (xx ?F → repeat xx (N+1)*16 times)
    Reads from input_path, writes decompressed data to output_path
    """
    if not os.path.exists(input_path):
        raise FileNotFoundError(f"Input file not found: {input_path}")

    with open(input_path, 'rb') as f_in:
        data = f_in.read()

    decompressed = decompress_rle_16(data)

    with open(output_path, 'wb') as f_out:
        f_out.write(decompressed)

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
