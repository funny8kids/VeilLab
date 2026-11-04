import type {
  Groth16Proof,
  ProverErrorData,
  ProverStage,
  ProverWorkerRequest,
  ProverWorkerResponse,
  WitnessInput,
} from "../lib/prover";

/**
 * Browser-local Groth16 prover.
 *
 * The witness is received through postMessage and stays in this worker. It is
 * never logged, persisted or sent to the API. Only the proof and the six public
 * signals are posted back to the page.
 */

const DEFAULT_WASM_URL = "/zk/membership.wasm";
const DEFAULT_ZKEY_URL = "/zk/membership.zkey";
const DEFAULT_VKEY_URL = "/zk/verification_key.json";

/** Silence snarkjs' own logger so no witness-adjacent diagnostics are printed. */
const silentLogger = {
  debug: () => undefined,
  info: () => undefined,
  warn: () => undefined,
  error: () => undefined,
};

interface FetchedArtifact {
  bytes: Uint8Array;
}

class WorkerProverError extends Error {
  code: ProverErrorData["code"];

  constructor(code: ProverErrorData["code"], message: string) {
    super(message);
    this.name = "WorkerProverError";
    this.code = code;
  }
}

function post(message: ProverWorkerResponse): void {
  (self as unknown as { postMessage: (value: unknown) => void }).postMessage(
    message,
  );
}

function progress(stage: ProverStage): void {
  post({ type: "progress", stage });
}

async function fetchArtifact(
  url: string,
  label: string,
): Promise<FetchedArtifact> {
  let response: Response;
  try {
    response = await fetch(url, { cache: "no-store" });
  } catch {
    throw new WorkerProverError(
      "ARTIFACT_MISSING",
      `The ${label} artifact could not be fetched.`,
    );
  }

  const contentType = response.headers.get("content-type") ?? "";
  // Dev servers often answer missing static files with the SPA index.html.
  if (!response.ok || contentType.includes("text/html")) {
    throw new WorkerProverError(
      "ARTIFACT_MISSING",
      `The ${label} artifact is missing at ${url}.`,
    );
  }

  const bytes = new Uint8Array(await response.arrayBuffer());
  if (bytes.byteLength === 0) {
    throw new WorkerProverError(
      "ARTIFACT_MISSING",
      `The ${label} artifact is empty at ${url}.`,
    );
  }
  return { bytes };
}

async function fetchVerificationKey(url: string): Promise<unknown> {
  const artifact = await fetchArtifact(url, "verification key");
  try {
    return JSON.parse(new TextDecoder().decode(artifact.bytes)) as unknown;
  } catch {
    throw new WorkerProverError(
      "ARTIFACT_MISSING",
      "The verification key is not valid JSON.",
    );
  }
}

function errorData(error: unknown): ProverErrorData {
  if (error instanceof WorkerProverError) {
    return { code: error.code, message: error.message };
  }
  if (error instanceof Error) {
    // Do not echo the witness/input. snarkjs errors describe the circuit or
    // artifact, not the private field values.
    return {
      code: "PROVE_FAILED",
      message: error.message.slice(0, 500),
    };
  }
  return { code: "PROVE_FAILED", message: "The local prover failed." };
}

async function handleProve(request: ProverWorkerRequest): Promise<void> {
  const started = performance.now();
  const wasmUrl = request.wasmUrl || DEFAULT_WASM_URL;
  const zkeyUrl = request.zkeyUrl || DEFAULT_ZKEY_URL;
  const vkeyUrl = request.vkeyUrl || DEFAULT_VKEY_URL;
  const input: WitnessInput = request.input;

  progress("loading");

  // Load snarkjs and the artifacts together. This keeps snarkjs out of the
  // normal app bundle: it is only fetched when a withdrawal is actually proved.
  const [snarkjs, wasm, zkey, verificationKey] = await Promise.all([
    import("snarkjs"),
    fetchArtifact(wasmUrl, "wasm"),
    fetchArtifact(zkeyUrl, "zkey"),
    fetchVerificationKey(vkeyUrl),
  ]);

  progress("proving");
  const { proof, publicSignals } = await snarkjs.groth16.fullProve(
    input,
    wasm.bytes,
    zkey.bytes,
    silentLogger,
  );

  progress("verifying");
  const verified = await snarkjs.groth16.verify(
    verificationKey,
    publicSignals,
    proof as Groth16Proof,
    silentLogger,
  );

  post({
    type: "done",
    proof: proof as Groth16Proof,
    publicSignals,
    durationMs: performance.now() - started,
    verified,
  });
}

self.onmessage = (event: MessageEvent<ProverWorkerRequest>) => {
  const request = event.data;
  if (!request || request.type !== "prove") {
    post({
      type: "error",
      error: {
        code: "WORKER_FAILED",
        message: "The prover worker received an unsupported message.",
      },
    });
    return;
  }

  void handleProve(request).catch((error: unknown) => {
    post({ type: "error", error: errorData(error) });
  });
};
