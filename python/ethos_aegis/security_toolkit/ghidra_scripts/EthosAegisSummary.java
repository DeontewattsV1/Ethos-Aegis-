// Ethos Aegis: static, content-free summary for an operator-authorized binary.
// @category EthosAegis
import ghidra.app.script.GhidraScript;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Paths;

public class EthosAegisSummary extends GhidraScript {
    @Override
    public void run() throws Exception {
        String[] args = getScriptArgs();
        if (args.length != 1) {
            throw new IllegalArgumentException("One output path is required.");
        }
        int functions = currentProgram.getFunctionManager().getFunctionCount();
        int imports = 0;
        ghidra.program.model.symbol.SymbolIterator symbols = currentProgram.getSymbolTable().getExternalSymbols();
        while (symbols.hasNext()) { symbols.next(); imports++; }
        long executableBytes = 0;
        for (ghidra.program.model.mem.MemoryBlock block : currentProgram.getMemory().getBlocks()) {
            if (block.isExecute()) executableBytes += block.getSize();
        }
        String summary = "{\"schema\":\"ethos-aegis.ghidra.v1\",\"functions\":" + functions
            + ",\"imports\":" + imports + ",\"executable_bytes\":" + executableBytes + "}";
        Files.write(Paths.get(args[0]), summary.getBytes(StandardCharsets.UTF_8));
    }
}
