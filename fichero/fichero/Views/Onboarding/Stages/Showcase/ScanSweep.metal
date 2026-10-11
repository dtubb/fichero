// The one shader of Set Up's stage pictures (#5668, `source.onboard.stages.shows-what-it-does`): a soft band of light
// sweeping down the page, for Prepare Images (the scan being cleaned) and Read (the line being read).
#include <metal_stdlib>
#include <SwiftUI/SwiftUI_Metal.h>
using namespace metal;

/// `sweepY`: the band's centre in points; `band`: its half height; `lift`: how much it brightens, 0 to 1.
[[ stitchable ]] half4 scanSweep(float2 position, half4 color, float sweepY, float band, float lift) {
    float distance = abs(position.y - sweepY);
    float glow = saturate(1.0 - distance / max(band, 1.0));
    half3 lit = color.rgb + half3(glow * lift) * color.a;
    return half4(min(lit, half3(color.a)), color.a);
}
