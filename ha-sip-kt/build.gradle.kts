// Root build file. Actual build configuration lives in each module's build.gradle.kts.
// Plugin versions are declared once here (via the version catalog) and applied
// without a version in each subproject to avoid Gradle loading the Kotlin plugin
// multiple times.
plugins {
    alias(libs.plugins.kotlin.jvm) apply false
    alias(libs.plugins.kotlin.serialization) apply false
    alias(libs.plugins.shadow) apply false
    alias(libs.plugins.ktlint) apply false
}
