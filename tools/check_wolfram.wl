(* Headless built-in capability check. No notebooks, third-party imports or front end. *)
$HistoryLength = 0;
outcome = TimeConstrained[
  Quiet[Check[
    Module[{x, symbolic, integral, residual, ok},
      symbolic = FullSimplify[Sin[x]^2 + Cos[x]^2 - 1, Assumptions -> Element[x, Reals]];
      integral = NIntegrate[x^2, {x, 0, 1}, WorkingPrecision -> 30];
      residual = Abs[integral - N[1/3, 30]];
      ok = TrueQ[symbolic === 0 && residual < 10^-20];
      Print["WOLFRAM_VERSION=" <> $Version];
      Print["SYSTEM_ID=" <> $SystemID];
      Print["SYMBOLIC_RESIDUAL=" <> ToString[symbolic, InputForm]];
      Print["INTEGRAL_RESIDUAL=" <> ToString[residual, InputForm]];
      Print[If[ok, "SCAFFOLD_WOLFRAM_CHECK=PASS", "SCAFFOLD_WOLFRAM_CHECK=FAIL"]];
      If[ok, 0, 1]
    ],
    Print["SCAFFOLD_WOLFRAM_CHECK=ERROR"]; 2
  ]],
  20,
  Print["SCAFFOLD_WOLFRAM_CHECK=TIMEOUT"]; 3
];
Exit[outcome];
