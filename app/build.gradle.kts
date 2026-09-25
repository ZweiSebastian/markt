plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
}

android {
    namespace = "de.seba.markt"
    compileSdk = 34

    // Fester Schlüssel: so lassen sich neue Versionen über die alte installieren, ohne dass Daten verloren gehen
    signingConfigs {
        create("fixed") {
            storeFile = file("markt.keystore")
            storePassword = "android"
            keyAlias = "markt"
            keyPassword = "android"
        }
    }

    defaultConfig {
        applicationId = "de.seba.markt"
        minSdk = 28
        targetSdk = 34
        versionCode = 9
        versionName = "1.8"
    }

    buildTypes {
        debug {
            signingConfig = signingConfigs.getByName("fixed")
        }
        release {
            isMinifyEnabled = false
            signingConfig = signingConfigs.getByName("fixed")
        }
    }
    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
    kotlinOptions {
        jvmTarget = "17"
    }
}

dependencies {
    implementation("androidx.core:core-ktx:1.13.1")
    implementation("androidx.activity:activity-ktx:1.9.2")
}
