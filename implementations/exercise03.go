package main

import (
	"crypto/sha256"
	"encoding"
	"encoding/binary"
	"encoding/hex"
	"fmt"
	"os"
	"runtime"
	"sync"
	"sync/atomic"
	"time"
)

const (
	outputPath           = "solutions/exercise03.txt"
	minTimestamp         = uint32(1230999305)
	progressBatchSize    = uint64(1_000_000)
	progressPrintSeconds = 2
	foundCheckMask       = uint64(1<<12 - 1) // poll found every 4096 hashes
)

var (
	version       = mustDecode("00000002")
	previousBlock = mustDecode("00000000d1145790a8694403d4063f323d499e655c83426834d4ce2f8dd4a2ee")
	merkleRoot    = mustDecode("c0a692de10b69e2381a2856dcb0d0736dcd307bf25af7ce74831bf25793de626")
	target        = mustDecode("00000000ffff0000000000000000000000000000000000000000000000000000")
)

type result struct {
	header []byte
	hash   [32]byte
	nonce  uint64
}

func mustDecode(value string) []byte {
	decoded, err := hex.DecodeString(value)
	if err != nil {
		panic(err)
	}
	return decoded
}

// buildPrefix returns the constant 72-byte header prefix (everything before the nonce).
func buildPrefix(timestamp uint32) []byte {
	prefix := make([]byte, 0, 72)
	prefix = append(prefix, version...)
	prefix = append(prefix, previousBlock...)
	prefix = append(prefix, merkleRoot...)
	timeBytes := make([]byte, 4)
	binary.BigEndian.PutUint32(timeBytes, timestamp)
	prefix = append(prefix, timeBytes...)
	return prefix
}

// meetsTarget is a cheap inlineable replacement for the byte-loop compare.
// target = 00000000ffff0000...; 4 leading zero bytes is decisive in all but a
// vanishingly rare boundary case, which falls through to a full compare.
func meetsTarget(hash [32]byte) bool {
	if binary.BigEndian.Uint32(hash[0:4]) != 0 {
		return false
	}
	top := binary.BigEndian.Uint16(hash[4:6])
	if top < 0xffff {
		return true
	}
	if top > 0xffff {
		return false
	}
	for i := 6; i < 32; i++ {
		if hash[i] != 0 {
			return false
		}
	}
	return true
}

func worker(
	prefix []byte,
	midstate []byte,
	workerID int,
	workerCount int,
	found *atomic.Bool,
	attempts *atomic.Uint64,
	results chan<- result,
	wg *sync.WaitGroup,
) {
	defer wg.Done()

	header := make([]byte, 80)
	copy(header, prefix)
	tail := header[64:80]       // 16 bytes: tail of block 1's data + timestamp + nonce
	nonceBytes := header[72:80] // nonce lives entirely inside the second SHA-256 block

	dig := sha256.New()
	un := dig.(encoding.BinaryUnmarshaler)

	var out [32]byte
	nonce := uint64(workerID)
	step := uint64(workerCount)
	localAttempts := uint64(0)

	for {
		binary.BigEndian.PutUint64(nonceBytes, nonce)

		// Resume from the cached state after the constant first 64 bytes,
		// then hash only the final 16-byte block instead of all 80 bytes.
		un.UnmarshalBinary(midstate)
		dig.Write(tail)
		dig.Sum(out[:0])
		localAttempts++

		if meetsTarget(out) {
			if found.CompareAndSwap(false, true) {
				solvedHeader := make([]byte, len(header))
				copy(solvedHeader, header)
				attempts.Add(localAttempts)
				results <- result{header: solvedHeader, hash: out, nonce: nonce}
			}
			return
		}

		if localAttempts&foundCheckMask == 0 {
			if found.Load() {
				attempts.Add(localAttempts)
				return
			}
			if localAttempts >= progressBatchSize {
				attempts.Add(localAttempts)
				localAttempts = 0
			}
		}

		nonce += step
	}
}

func writeSolution(header []byte) error {
	return os.WriteFile(outputPath, []byte(hex.EncodeToString(header)+"\n"), 0644)
}

func main() {
	workerCount := runtime.NumCPU()
	runtime.GOMAXPROCS(workerCount)

	prefix := buildPrefix(minTimestamp)

	// Cache the SHA-256 state after the constant first 64 bytes, once.
	seed := sha256.New()
	seed.Write(prefix[:64])
	midstate, err := seed.(encoding.BinaryMarshaler).MarshalBinary()
	if err != nil {
		panic(err)
	}

	found := &atomic.Bool{}
	attempts := &atomic.Uint64{}
	results := make(chan result, 1)
	var wg sync.WaitGroup

	for workerID := 0; workerID < workerCount; workerID++ {
		wg.Add(1)
		go worker(prefix, midstate, workerID, workerCount, found, attempts, results, &wg)
	}

	startedAt := time.Now()
	ticker := time.NewTicker(progressPrintSeconds * time.Second)
	defer ticker.Stop()
	fmt.Printf("Mining with %d workers...\n", workerCount)

	var solved result
	for {
		select {
		case solved = <-results:
			wg.Wait()
			elapsed := time.Since(startedAt).Seconds()
			totalAttempts := attempts.Load()
			rate := float64(totalAttempts) / elapsed
			if err := writeSolution(solved.header); err != nil {
				fmt.Fprintf(os.Stderr, "Failed to write solution: %v\n", err)
				os.Exit(1)
			}
			fmt.Printf("Solved in %.2fs\n", elapsed)
			fmt.Printf("Attempts: %d\n", totalAttempts)
			fmt.Printf("Hash rate: %.0f/s\n", rate)
			fmt.Printf("Timestamp: %d\n", minTimestamp)
			fmt.Printf("Nonce: %d\n", solved.nonce)
			fmt.Printf("Block hash: %s\n", hex.EncodeToString(solved.hash[:]))
			fmt.Printf("Header: %s\n", hex.EncodeToString(solved.header))
			return
		case <-ticker.C:
			elapsed := time.Since(startedAt).Seconds()
			totalAttempts := attempts.Load()
			rate := float64(totalAttempts) / elapsed
			fmt.Printf("Attempts: %d | Hash rate: %.0f/s\n", totalAttempts, rate)
		}
	}
}
