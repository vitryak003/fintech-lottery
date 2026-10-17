import { mkdir, readFile, writeFile, readdir } from "node:fs/promises";
import path from "node:path";

async function findArtifact(directory, name) {
  for (const entry of await readdir(directory, { withFileTypes: true })) {
    const filename = path.join(directory, entry.name);
    if (entry.isDirectory()) {
      const found = await findArtifact(filename, name);
      if (found) return found;
    } else if (entry.name === `${name}.json`) {
      const data = JSON.parse(await readFile(filename, "utf8"));
      if (data.contractName === name && Array.isArray(data.abi)) return data;
    }
  }
}

const deployed = JSON.parse(await readFile(
  "ignition/deployments/chain-31337/deployed_addresses.json", "utf8",
));
await mkdir("python/abi", { recursive: true });
const addresses = { chainId: 31337, rpcUrl: "http://127.0.0.1:8545" };
for (const name of ["Lottery", "PrizeDistributor"]) {
  const artifact = await findArtifact("artifacts", name);
  if (!artifact) throw new Error(`Missing artifact: ${name}`);
  const address = deployed[`LotteryModule#${name}`];
  if (!address) throw new Error(`Missing address: ${name}`);
  addresses[name] = address;
  await writeFile(`python/abi/${name}.json`, JSON.stringify(artifact.abi, null, 2) + "\n");
}
await writeFile("python/contract_addresses.json", JSON.stringify(addresses, null, 2) + "\n");
console.log("Exported contract addresses and ABI to python/");
