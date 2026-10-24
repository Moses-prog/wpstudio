import http.server
import socketserver
import os
import json
import asyncio
import traceback
from ai_engine import generate_character_turnaround

PORT = 8085
WEB_DIR = os.path.join(os.path.dirname(__file__), "webapp")

class StudioHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=WEB_DIR, **kwargs)

    def do_POST(self):
        if self.path == "/api/forge_character":
            try:
                content_len = int(self.headers.get("Content-Length", 0))
                post_body = self.rfile.read(content_len).decode("utf-8")
                data = json.loads(post_body) if post_body else {}

                name = data.get("name", "Kemi").strip() or "Kemi"
                age = data.get("age", "28")
                gender = data.get("gender", "Female")
                complexion = data.get("complexion", "Medium brown")
                nose_type = data.get("noseType", "Broad / Wide")
                hairstyle = data.get("hairstyle", "Braids")
                custom_hair = data.get("customHairstyle", "").strip()
                hair_color = data.get("hairColor", "#000000")
                body_size = data.get("bodySize", "Average")
                height = data.get("height", "Tall")
                expression = data.get("expression", "Happy")
                outfit_style = data.get("outfitStyle", "Ankara")
                custom_outfit = data.get("customOutfit", "").strip()
                background = data.get("background", "Neutral studio")
                lighting = data.get("lighting", "Studio")
                art_style = data.get("artStyle", "Realistic")
                purpose = data.get("purpose", "Film")

                # Resolved trait descriptions
                effective_hair = custom_hair if custom_hair else f"{hairstyle} styled in {hair_color} shade"
                effective_outfit = custom_outfit if (outfit_style == "Custom" or custom_outfit) else f"{outfit_style} traditional bespoke attire"

                full_desc = (
                    f"Character: {name}, {age}-year-old {gender}. "
                    f"Complexion: {complexion} Nigerian skin tone. "
                    f"Nose type: {nose_type}. "
                    f"Hairstyle: {effective_hair} (color {hair_color}). "
                    f"Body Build: {body_size} frame, {height} stature. "
                    f"Facial Expression: {expression}. "
                    f"Outfit: {effective_outfit}. "
                    f"Background environment: {background}. "
                    f"Lighting: {lighting} setup. "
                    f"Art Direction: {art_style}. "
                    f"Target Media Purpose: {purpose}."
                )

                print(f"[Forge API] Received request for {name} ({art_style})...")

                # Attempt Generation via Gemini
                ai_res = None
                try:
                    ai_res = asyncio.run(generate_character_turnaround(full_desc, style=art_style))
                except Exception as ex:
                    print(f"[Forge API] Gemini call error: {ex}. Using local studio compiler fallback...")

                if not ai_res or not ai_res.get("master_9panel_sheet_prompt"):
                    # High-intelligence local deterministic studio compiler fallback
                    master_prompt = (
                        f"Character model sheet, turnaround reference sheet, 3x3 grid layout, 9 distinct panels of the same character: "
                        f"[1] FRONT full body standing relaxed A-pose at eye-level, "
                        f"[2] THREE-QUARTER full body standing at 45-degree angle showing silhouette, "
                        f"[3] PROFILE 90-degree full body standing showing posture and spinal alignment, "
                        f"[4] BACK full body standing rear view showing hair drape and dress silhouette, "
                        f"[5] FRONT CLOSE-UP headshot portrait with {expression.lower()} expression, "
                        f"[6] THREE-QUARTER CLOSE-UP headshot at 45-degree angle showing cheekbone and jawline definition, "
                        f"[7] PROFILE CLOSE-UP headshot true 90-degree side profile showing {nose_type.lower()} nose bridge and lips, "
                        f"[8] HAIRSTYLE DETAIL macro close-up of back of head showing {effective_hair}, "
                        f"[9] WARDROBE DETAIL macro close-up of torso and neckline showing {effective_outfit}. "
                        f"Featuring {name}, {age}-year-old {gender}, {complexion.lower()} skin tone, {height.lower()} {body_size.lower()} build, {effective_hair}, {effective_outfit}. "
                        f"Uniform neutral light grey studio background, {lighting.lower()} multi-point cinematic lighting, "
                        f"Raytracing, Subsurface Scattering (SSS), 8k resolution, identical facial proportions across all panels, zero morphological drift, no text, no watermarks --ar 9:16 --v 6.1 --stylize 250"
                    )

                    consistency_bible = (
                        f"DEMOGRAPHICS & BIOMETRICS: {name}, {age}-year-old {gender}, {height} height, {body_size} build.\n"
                        f"COMPLEXION & SKIN SHADER: {complexion} tone with realistic melanin gradient, authentic epidermal micro-pore displacement, and soft subsurface scattering (SSS) light diffusion.\n"
                        f"CRANIOFACIAL LANDMARKS: {nose_type} nasal bridge, sculpted cheekbones, balanced lip contour with natural sheen, {expression} expression.\n"
                        f"HAIR ARCHITECTURE: {effective_hair} with clean geometric scalp sectioning, hex color {hair_color}.\n"
                        f"WARDROBE CRAFTSMANSHIP: {effective_outfit} tailored with precise textile weave and crisp edge stitching.\n"
                        f"LIGHTING & ENVIRONMENT: {lighting} setup on {background} cyclorama backdrop, neutral color temperature, subtle rim light separating subject from background.\n"
                        f"IDENTITY CONTINUITY LOCK: Identical craniofacial landmarks and wardrobe architecture locked across all 9 panels."
                    )

                    ai_res = {
                        "character_name": name,
                        "visual_style": f"{art_style} / Studio Turnaround",
                        "consistency_bible": consistency_bible,
                        "master_9panel_sheet_prompt": master_prompt,
                        "angle_prompts": {
                            "front_full_body": f"Objective full body standing front view, eye-level, 50mm lens. {name}, {age}yo {gender}, {complexion} skin, {effective_hair}, wearing {effective_outfit}. Neutral {background}, soft {lighting} lighting, 8k --ar 9:16",
                            "three_quarter_full_body": f"Objective full body standing 45-degree three-quarter view. {name}, displaying silhouette depth, {effective_hair}, wearing {effective_outfit}. Neutral {background}, soft {lighting} lighting, subtle rim light, 8k --ar 9:16",
                            "profile_full_body": f"Objective full body standing strict 90-degree side profile. {name}, showing posture and garment drape, {effective_hair}, wearing {effective_outfit}. Neutral {background}, 8k --ar 9:16",
                            "back_full_body": f"Objective full body standing back view. {name}, showing rear garment construction and hair flow down spine. Neutral {background}, 8k --ar 9:16",
                            "front_close_up": f"Close-up headshot portrait facing directly forward. {name}, {complexion} skin, {expression} expression, {nose_type} nose bridge, {effective_hair}. Ultra-detailed skin pores, 8k --ar 1:1",
                            "three_quarter_close_up": f"Close-up headshot portrait at 45-degree angle. Highlighting cheekbone curvature and jawline definition for {name}. {complexion} skin, {effective_hair}, 8k --ar 1:1",
                            "profile_close_up": f"Strict 90-degree side profile headshot portrait. Focusing on {nose_type} nose bridge, lip profile, and ear anatomy for {name}. 8k --ar 1:1",
                            "hairstyle_detail": f"Macro close-up of back of head for {name}. Showcasing {effective_hair} with clean scalp sectioning and fine texture. Studio rim lighting, 8k --ar 1:1",
                            "wardrobe_detail": f"Macro textile craftsmanship view of {name}'s attire: {effective_outfit}. Fine fabric weave, collar stitching, and material texture. Studio lighting, 8k --ar 1:1"
                        },
                        "action_prompt": f"Cinematic wide-angle dynamic 3D shot of {name} in {effective_outfit} in motion. Dramatic lighting, atmospheric particle effects, 8k --ar 16:9",
                        "recommended_midjourney_params": "--ar 9:16 --v 6.1 --stylize 250"
                    }

                response_data = {
                    "status": "success",
                    "character": ai_res,
                    "credits_used": 10,
                    "credits_remaining": 40
                }

                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(json.dumps(response_data).encode("utf-8"))
                print(f"[Forge API] Successfully forged {name}!")
            except Exception as e:
                traceback.print_exc()
                self.send_response(500)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.end_headers()
                self.wfile.write(json.dumps({"status": "error", "message": str(e)}).encode("utf-8"))
        else:
            self.send_response(404)
            self.end_headers()

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "POST, GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

def run():
    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.TCPServer(("", PORT), StudioHandler) as httpd:
        print(f"WP Studio CastLock 3D Mini App Server running at: http://localhost:{PORT}")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nShutting down server.")

if __name__ == "__main__":
    run()
