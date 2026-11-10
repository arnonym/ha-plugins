rootProject.name = "ha-sip-ng"

// gradle/libs.versions.toml is auto-detected as the "libs" version catalog.

include(":core")
include(":app")

// Docker-free, opt-in end-to-end suite: spawns two real ha-sip processes and puts
// a direct-IP SIP call between them. Its `test` task is a no-op unless run with
// -PintegrationTests (see integration-test/build.gradle.kts), so `./gradlew build`
// and CI stay unaffected.
include(":integration-test")
