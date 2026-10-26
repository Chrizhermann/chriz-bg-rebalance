-- Load diagnostic and correction commands only; native patching is explicitly requested later.
if EEex_Active then
    Infinity_DoFile("CBRTObs")
    Infinity_DoFile("CBRTFix")
    Infinity_DoFile("CBRTCor")
    Infinity_DoFile("CBRTCld")
end
