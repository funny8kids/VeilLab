/**
 * Minimal local typings for the subset of snarkjs 0.7.6 used by the worker.
 * snarkjs does not ship TypeScript declarations.
 */
declare module "snarkjs" {
  export interface Groth16Proof {
    pi_a: string[];
    pi_b: string[][];
    pi_c: string[];
    protocol?: string;
    curve?: string;
  }

  export interface Groth16ProveResult {
    proof: Groth16Proof;
    publicSignals: string[];
  }

  export const groth16: {
    fullProve(
      input: Record<string, unknown>,
      wasmFile: string | Uint8Array,
      zkeyFile: string | Uint8Array,
      logger?: unknown,
    ): Promise<Groth16ProveResult>;
    verify(
      verificationKey: unknown,
      publicSignals: string[],
      proof: Groth16Proof,
      logger?: unknown,
    ): Promise<boolean>;
  };
}
