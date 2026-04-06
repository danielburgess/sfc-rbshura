WINDOW_SIZE = 4096
MIN_MATCH_LENGTH = 3
TEST_BIT = 0x01


class LZSSState:
    def __init__(self):
        self.window = bytearray(WINDOW_SIZE)
        self.window_pos = 0xFEE

    def reset(self):
        self.window[:] = b"\x00" * WINDOW_SIZE
        self.window_pos = 0xFEE


def lzss_decompress_exact(
    compressed: bytes,
    start_pos: int,
    expected_output_size: int,
    allow_window_reset: bool = False
) -> bytes | None:
    state = LZSSState()
    input_pos = start_pos
    output = bytearray()

    comp_size = len(compressed)

    try:
        while len(output) < expected_output_size:
            # if input_pos >= comp_size:
            #     return None  # premature EOF

            code = compressed[input_pos]
            input_pos += 1

            for _ in range(8):
                # if len(output) >= expected_output_size:
                #     break

                if code & TEST_BIT:
                    # if input_pos >= comp_size:
                    #     return None
                    lit = compressed[input_pos]
                    input_pos += 1

                    output.append(lit)
                    state.window[state.window_pos] = lit
                    state.window_pos = (state.window_pos + 1) & 0xFFF
                else:
                    # if input_pos + 1 >= comp_size:
                    #     return None

                    lz1 = compressed[input_pos]
                    lz2 = compressed[input_pos + 1]
                    input_pos += 2

                    length = (lz2 & 0x0F) + MIN_MATCH_LENGTH
                    offset = (((lz2 & 0xF0) << 4) | lz1) & 0x0FFF

                    for _ in range(length):
                        # if len(output) >= expected_output_size:
                        #     break
                        byte = state.window[offset]
                        output.append(byte)
                        state.window[state.window_pos] = byte
                        state.window_pos = (state.window_pos + 1) & 0xFFF
                        offset = (offset + 1) & 0xFFF

                code >>= 1

        return bytes(output)

    except Exception as ex:
        print(repr(ex))
        return None


def find_lzss_start(
    compressed: bytes,
    expected_output_size: int,
    max_scan: int = 512
) -> int | None:
    for start in range(max_scan):
        out = lzss_decompress_exact(
            compressed,
            start,
            expected_output_size
        )
        if out is not None:
            return start
    return None


def lzss_decompress_with_resets(
    compressed: bytes,
    start_pos: int,
    expected_output: bytes
):
    state = LZSSState()
    input_pos = start_pos
    output = bytearray()

    last_flag_pos = None
    comp_size = len(compressed)

    while len(output) < len(expected_output):
        if input_pos >= comp_size:
            raise RuntimeError("Unexpected EOF")

        last_flag_pos = input_pos
        code = compressed[input_pos]
        input_pos += 1

        for _ in range(8):
            if len(output) >= len(expected_output):
                break

            expected_byte = expected_output[len(output)]

            if code & TEST_BIT:
                lit = compressed[input_pos]
                input_pos += 1

                if lit != expected_byte:
                    # Try window reset
                    state.reset()
                    return lzss_decompress_with_resets(
                        compressed,
                        last_flag_pos,
                        expected_output
                    )

                output.append(lit)
                state.window[state.window_pos] = lit
                state.window_pos = (state.window_pos + 1) & 0xFFF

            else:
                lz1 = compressed[input_pos]
                lz2 = compressed[input_pos + 1]
                input_pos += 2

                length = (lz2 & 0x0F) + MIN_MATCH_LENGTH
                offset = (((lz2 & 0xF0) << 4) | lz1) & 0x0FFF

                for _ in range(length):
                    if len(output) >= len(expected_output):
                        break
                    byte = state.window[offset]

                    if byte != expected_byte:
                        state.reset()
                        return lzss_decompress_with_resets(
                            compressed,
                            last_flag_pos,
                            expected_output
                        )

                    output.append(byte)
                    state.window[state.window_pos] = byte
                    state.window_pos = (state.window_pos + 1) & 0xFFF
                    offset = (offset + 1) & 0xFFF

            code >>= 1

    return bytes(output)


def load_file(file_path: str):
    with open(file_path, 'rb') as f:
        return f.read()


def test_decomp_size():
    compressed = load_file("title_screen_tile_map_C000_compressed.bin")
    expected = load_file("title_screen_tile_map_C000.bin")

    start = find_lzss_start(compressed, len(expected))
    print("LZSS stream starts at:", hex(start))

    decoded = lzss_decompress_with_resets(
        compressed,
        start,
        expected
    )

    assert decoded == expected



